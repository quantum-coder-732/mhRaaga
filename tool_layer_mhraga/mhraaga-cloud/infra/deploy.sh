#!/usr/bin/env bash
# Deploy mhRaaga to AWS (AWS_PROFILE, default mhraaga; ap-south-1): secrets -> SSM, Lambda package, CloudFormation, site -> S3, CloudFront invalidation.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
export AWS_PROFILE="${AWS_PROFILE:-mhraaga}" AWS_REGION="${AWS_REGION:-ap-south-1}" AWS_DEFAULT_REGION="${AWS_REGION:-ap-south-1}" AWS_PAGER=""
STACK=mhraaga
if [ -f "$ROOT/.env" ]; then _P="$AWS_PROFILE"; set -a; . "$ROOT/.env"; set +a; export AWS_PROFILE="$_P"; fi
ACCT=$(aws sts get-caller-identity --query Account --output text); echo "account $ACCT, region $AWS_REGION"

# 1. secrets live in SSM Parameter Store (SecureString), never in the repo or the template
[ -n "${OPENROUTER_API_KEY:-}" ] && aws ssm put-parameter --name /mhraaga/openrouter_key --type SecureString --overwrite --value "$OPENROUTER_API_KEY" >/dev/null
aws ssm get-parameter --name /mhraaga/jwt_secret >/dev/null 2>&1 || aws ssm put-parameter --name /mhraaga/jwt_secret --type SecureString --value "$(openssl rand -hex 32)" >/dev/null
aws ssm get-parameter --name /mhraaga/origin_secret >/dev/null 2>&1 || aws ssm put-parameter --name /mhraaga/origin_secret --type SecureString --value "$(openssl rand -hex 24)" >/dev/null
ORIGIN=$(aws ssm get-parameter --name /mhraaga/origin_secret --with-decryption --query Parameter.Value --output text)

# 2. Lambda package = API handler + the music engine layer
rm -rf "$HERE/build"; mkdir -p "$HERE/build/lambda"
cp "$HERE/api/handler.py" "$HERE/api/studio.py" "$HERE/api/team.py" "$HERE/api/voice.py" "$HERE/build/lambda/"
cp -r "$ROOT/music_engine_framework_layer/mhraaga_engine" "$HERE/build/lambda/"
rm -rf "$HERE/build/lambda/mhraaga_engine/agentic/data" "$HERE/build/lambda/mhraaga_engine/agentic"   # offline tooling, not needed at runtime
# real Box2D (pybox2d 2.3.10) for the Lambda runtime: python3.12 on x86_64. Without it the engine falls back to its pure-Python solver.
python3 -m pip download "Box2D==2.3.10" --only-binary=:all: --no-deps --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp --abi cp312 -d "$HERE/build/wheels" -q
unzip -q -o "$HERE"/build/wheels/Box2D-*.whl -d "$HERE/build/lambda"; rm -rf "$HERE/build/wheels"
find "$HERE/build" -name __pycache__ -prune -exec rm -rf {} +

# 3. package + deploy the stack
ART="mhraaga-artifacts-$ACCT-$AWS_REGION"
aws s3api head-bucket --bucket "$ART" 2>/dev/null || { aws s3api create-bucket --bucket "$ART" --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$ART" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true; }
aws cloudformation package --template-file "$HERE/infra/template.yaml" --s3-bucket "$ART" --output-template-file "$HERE/build/packaged.yaml" >/dev/null
aws cloudformation deploy --stack-name $STACK --template-file "$HERE/build/packaged.yaml" --capabilities CAPABILITY_IAM \
  --parameter-overrides OriginSecret="$ORIGIN" DomainName="${DOMAIN_NAME:-}" CertificateArn="${CERT_ARN:-}" --no-fail-on-empty-changeset
out() { aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
SITE=$(out SiteUrl); BUCKET=$(out SiteBucketName); DIST=$(out DistributionId); DIRECT=$(out ApiDirectUrl)

# 4. website
aws s3 sync "$HERE/web" "s3://$BUCKET" --delete --cache-control "public,max-age=300" --exclude ".DS_Store" --exclude "catalog/*" --exclude "library/*" --exclude "rules/*" --exclude "samples/*" --exclude "tts/*" >/dev/null
aws s3 cp "$HERE/web/index.html" "s3://$BUCKET/index.html" --cache-control "no-cache" --content-type "text/html; charset=utf-8" >/dev/null
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" >/dev/null

# 5. smoke test
echo "$SITE" > "$HERE/DEPLOY_URL.txt"
echo "site:  $SITE"; echo "api (direct, must be 403): $DIRECT/api/health"
curl -s -o /dev/null -w "direct api -> %{http_code}\n" "$DIRECT/api/health"
for i in 1 2 3 4 5 6; do c=$(curl -s -o /dev/null -w "%{http_code}" "$SITE/api/health"); echo "via CloudFront /api/health -> $c"; [ "$c" = 200 ] && break; sleep 10; done
