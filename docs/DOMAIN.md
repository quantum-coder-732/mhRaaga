# Putting mhraaga.in on the site

The site is served by CloudFront (`https://d1bka1wc4jd8uy.cloudfront.net`). A custom domain needs a certificate and two DNS records. The template already has the switches (`DomainName`, `CertificateArn`).

1. **Certificate (must be in us-east-1, even though the stack is in ap-south-1).**
   ```bash
   aws acm request-certificate --region us-east-1 --domain-name mhraaga.in --subject-alternative-names www.mhraaga.in --validation-method DNS --profile default
   aws acm describe-certificate --region us-east-1 --certificate-arn <ARN> --query 'Certificate.DomainValidationOptions[].ResourceRecord'
   ```
2. **Validate:** add the CNAME records it prints at your domain registrar's DNS. Wait until the status is `ISSUED` (a few minutes).
3. **Deploy with the domain:**
   ```bash
   DOMAIN_NAME=mhraaga.in CERT_ARN=<ARN> AWS_PROFILE=default bash tool_layer_mhraga/mhraaga-cloud/infra/deploy.sh
   ```
   (or put `DOMAIN_NAME=` and `CERT_ARN=` in `.env`). The output `CloudFrontDomain` is your CloudFront address.
4. **Point DNS at CloudFront:** `www` → CNAME to the CloudFront address. The bare `mhraaga.in` needs an ALIAS/ANAME record (Route 53 offers this as an A/AAAA alias; many registrars do not). If your registrar has no ALIAS, move the domain's DNS to Route 53 (create a hosted zone, change the nameservers at the registrar, add the alias records).
5. Test `https://mhraaga.in`. HSTS is on, so keep HTTPS working before announcing it.

Leaving the two variables empty keeps the CloudFront address, so nothing breaks until you are ready. Every redeploy must pass them, or the aliases are removed.
