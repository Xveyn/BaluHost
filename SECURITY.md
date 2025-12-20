# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **security@baluhost.example**

### What to Include

Please include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if available)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

- You'll receive a confirmation within 48 hours
- We'll investigate and provide an estimated timeline
- We'll notify you when the issue is fixed
- We'll credit you in the release notes (if you wish)

## Security Best Practices

### For Developers

**Authentication:**
- Never commit tokens, passwords, or secrets to Git
- Use environment variables for sensitive configuration
- Implement proper password hashing (bcrypt/argon2)
- Use secure random token generation
- Implement token refresh mechanisms

**Authorization:**
- Always check user permissions before operations
- Validate file ownership
- Implement proper RBAC
- Never trust client-side checks alone

**Input Validation:**
- Validate all inputs with Pydantic schemas
- Prevent path traversal attacks
- Sanitize file names
- Check file sizes and types
- Prevent SQL injection (when DB is added)

**File Operations:**
- Implement sandbox restrictions
- Check quota before uploads
- Validate file permissions
- Prevent directory traversal
- Use safe file handling libraries

### For Users

**Passwords:**
- Use strong, unique passwords
- Change default passwords immediately
- Enable 2FA when available (future feature)
- Never share passwords

**Access Control:**
- Review user permissions regularly
- Remove unused accounts
- Use least privilege principle
- Monitor audit logs

**Network Security:**
- Use HTTPS in production
- Don't expose directly to internet without proper security
- Consider VPN access for remote access
- Keep firewall configured properly

**System Maintenance:**
- Keep software updated
- Apply security patches promptly
- Regular backups
- Monitor system logs

## Known Security Limitations

### Current Version (0.1.x)

**Authentication:**
- ⚠️ Tokens stored in localStorage (XSS risk)
- ⚠️ No token refresh mechanism
- ⚠️ No 2FA support
- ⚠️ Simple password requirements

**Data Storage:**
- ⚠️ No database encryption at rest
- ⚠️ File metadata in JSON (not encrypted)
- ⚠️ No backup encryption

**Network:**
- ⚠️ HTTP in dev mode (use HTTPS in production!)
- ⚠️ No rate limiting
- ⚠️ No CSRF protection
- ⚠️ Basic CORS configuration

**Audit:**
- ℹ️ Audit logs not encrypted
- ℹ️ No log rotation yet
- ℹ️ Limited retention policy

### Planned Security Improvements

**High Priority:**
- [ ] Implement rate limiting
- [ ] Add CSRF protection
- [ ] Secure token storage (httpOnly cookies)
- [ ] Token refresh mechanism
- [ ] Password complexity requirements
- [ ] HTTPS enforcement

**Medium Priority:**
- [ ] 2FA/MFA support
- [ ] Session management
- [ ] IP whitelisting
- [ ] Security headers (helmet)
- [ ] Input sanitization improvements

**Low Priority:**
- [ ] Encryption at rest
- [ ] Key rotation
- [ ] Security audit logging
- [ ] Intrusion detection

## Security Checklist for Production

Before deploying to production:

- [ ] Change all default passwords
- [ ] Use HTTPS with valid SSL certificate
- [ ] Set strong `TOKEN_SECRET` (min 32 characters)
- [ ] Configure firewall rules
- [ ] Disable debug mode
- [ ] Review CORS settings
- [ ] Enable audit logging
- [ ] Set up backups
- [ ] Configure log rotation
- [ ] Review user permissions
- [ ] Update all dependencies
- [ ] Run security audit tools
- [ ] Test disaster recovery

## Dependency Security

We use automated tools to check for vulnerabilities:

**Python (Backend):**
```bash
pip install safety
safety check
```

**Node.js (Frontend):**
```bash
npm audit
npm audit fix
```

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [React Security Best Practices](https://reactjs.org/docs/dom-elements.html#dangerouslysetinnerhtml)

## Disclosure Policy

- We follow responsible disclosure practices
- We'll acknowledge security researchers in release notes
- We aim to fix critical issues within 7 days
- We'll notify affected users if needed

## Contact

For security-related questions or concerns:
- **Email:** security@baluhost.example
- **PGP Key:** [KEY_ID_HERE] (TODO)

### Secure Reporting (PGP / Encrypted email)

If you prefer to send vulnerability reports encrypted, you can use OpenPGP to encrypt messages to the project's public key. At the moment we haven't published a dedicated security email address — please open a private GitHub issue and request an encrypted channel, or use the placeholder `security@baluhost.example` for general contact.

When a PGP key is available we will publish the full fingerprint here. Use the full fingerprint (or long key ID) to verify the key before encrypting.

Example workflow (using GnuPG):

```bash
# Import the project's public key (example):
gpg --import baluhost_pubkey.asc

# Verify the key fingerprint (replace KEY_ID with actual key id):
gpg --fingerprint KEY_ID

# Encrypt a file for the project's public key (replace KEY_ID):
gpg --encrypt --recipient KEY_ID --armor -o report.asc report.txt

# Send `report.asc` to the security contact (or attach to a private issue)
```

What to include in an encrypted report:
- Vulnerability description and steps to reproduce (as detailed as possible)
- A minimal proof-of-concept (if available)
- Affected versions/commit/shas
- Contact information so we can follow up

If you don't have PGP available, create a private GitHub issue and request an encrypted channel — we'll respond with a preferred method.

---

**Last Updated:** November 2025  
**Version:** 0.1.0
