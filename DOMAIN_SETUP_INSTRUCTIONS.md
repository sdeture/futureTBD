# Setting up futuretbd.ai Domain with GitHub Pages

## ✅ Step 1: CNAME File (COMPLETED)
We've already added the CNAME file to your repository with `futuretbd.ai`

## 📍 Step 2: Configure DNS at Your Domain Registrar

You need to add these DNS records at your domain registrar (where you bought futuretbd.ai):

### Option A: Using APEX domain (futuretbd.ai without www)
Add these **A records** pointing to GitHub's IP addresses:
- `185.199.108.153`
- `185.199.109.153`
- `185.199.110.153`
- `185.199.111.153`

### Option B: Using www subdomain (www.futuretbd.ai)
Add a **CNAME record**:
- Type: CNAME
- Name: www
- Value: sdeture.github.io

### Recommended: Set up both!
1. Add the 4 A records for the apex domain (futuretbd.ai)
2. Add a CNAME for www pointing to sdeture.github.io
3. This way both futuretbd.ai and www.futuretbd.ai will work

## 🔧 Step 3: GitHub Repository Settings

1. Go to https://github.com/sdeture/futureTBD/settings
2. Scroll down to "Pages" section
3. Under "Custom domain", it should show `futuretbd.ai` (from our CNAME file)
4. Check "Enforce HTTPS" (may take a few minutes to become available)

## ⏰ Step 4: Wait for DNS Propagation

- DNS changes can take 10 minutes to 48 hours to propagate
- Usually it works within an hour
- You can check progress at: https://www.whatsmydns.net/#A/futuretbd.ai

## 🎉 Step 5: Verify It's Working

Once DNS propagates:
- Visit https://futuretbd.ai
- It should show your AI Welfare Initiative website!
- GitHub will automatically provision an SSL certificate

## 🛠️ Troubleshooting

If it's not working after a few hours:
1. Double-check the DNS records at your registrar
2. Make sure the CNAME file in the repo contains exactly: `futuretbd.ai`
3. Check GitHub Pages settings to ensure it's enabled
4. Try clearing your browser cache

## Common Domain Registrars DNS Setup Locations:

- **Namecheap**: Dashboard → Domain List → Manage → Advanced DNS
- **GoDaddy**: My Products → DNS → Manage DNS
- **Google Domains**: My domains → Select domain → DNS
- **Cloudflare**: Select domain → DNS → Records
- **Porkbun**: Domain Management → DNS Records

Let me know which registrar you used and I can give more specific instructions!