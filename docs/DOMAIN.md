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

## Hostinger, step by step (certificate already requested)

Certificate ARN: `arn:aws:acm:us-east-1:877157050453:certificate/67556949-10e1-4adc-ad8b-b928dac89935` (status `PENDING_VALIDATION` until step 1 is done).

**1. Validation records.** In hPanel go to Domains, then DNS / Nameservers, then DNS records, and add two CNAME records. In Hostinger the *Name* field is the host without `.mhraaga.in`, and the trailing dot on the value can be left off.

| Type  | Name | Target |
|-------|------|--------|
| CNAME | `_8809945cbe58b3dcd6f488916d07a78a` | `_ddb9d39576eca5dbf0938ee79835fc7d.wzccmgtwzk.acm-validations.aws` |
| CNAME | `_16c9c25aea6b504a5aa913bc7388ebd2.www` | `_132bcc837ba0438be604e3b01b341c51.wzccmgtwzk.acm-validations.aws` |

Check with `aws acm describe-certificate --region us-east-1 --certificate-arn <ARN> --query Certificate.Status` until it says `ISSUED`.

**2. Deploy with the domain:** `DOMAIN_NAME=mhraaga.in CERT_ARN=<ARN> AWS_PROFILE=default bash tool_layer_mhraga/mhraaga-cloud/infra/deploy.sh`

**3. Site records** (after step 2):

| Type  | Name  | Target |
|-------|-------|--------|
| CNAME | `www` | `d1bka1wc4jd8uy.cloudfront.net` |

Delete any existing `www` A, AAAA or CNAME record first (a name cannot hold a CNAME and another record).
For the bare `mhraaga.in`: the DNS standard does not allow a CNAME at the root. If Hostinger offers an ALIAS or ANAME record, use it with the same target. If it only offers A/AAAA, use Hostinger's domain forwarding to send `mhraaga.in` to `https://www.mhraaga.in`, or move DNS to Route 53 (nameservers at Hostinger, aliases in Route 53).
