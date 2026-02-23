# SOCIAL IMPACT LICENSE - IMPLEMENTATION GUIDE

## 🎯 Quick Start: What You Need to Do

You now have **four professional documents** for your dual-licensing social impact model. Before you can use them, you must **customize** the placeholder fields and **get legal review**.

---

## 📋 STEP 1: CUSTOMIZE ALL PLACEHOLDERS

Search for and replace the following placeholders across **all four documents**:

### Required Replacements:

| Placeholder | Replace With | Example |
|-------------|--------------|---------|
| `[INSERT PROJECT NAME]` | Your software's official name | "Acme Analytics Platform" |
| `[INSERT LEGAL NAME/ENTITY]` | Your legal name or company | "Jane Doe" or "Acme Software LLC" |
| `[INSERT CHARITY NAME]` | Full legal name of the charity | "Electronic Frontier Foundation" |
| `[INSERT CHARITY/CAUSE]` | Brief description of the cause | "digital privacy and civil liberties" |
| `[INSERT CHARITABLE PURPOSE]` | Charity's mission | "defending digital rights and free expression" |
| `[INSERT CONTACT EMAIL]` | Your business email | "licensing@acmesoftware.com" |
| `[INSERT COMPLIANCE EMAIL]` | Email for transparency inquiries | "compliance@acmesoftware.com" |
| `[INSERT WEBSITE]` | Your project website | "https://acmesoftware.com" |
| `[INSERT PURCHASE LINK]` | Where users buy the $49 license | "https://acmesoftware.com/buy" |
| `[INSERT BUSINESS ADDRESS]` | Your legal address (if required) | "123 Main St, San Francisco, CA 94105" |
| `[INSERT JURISDICTION]` | Your legal jurisdiction | "the State of California" or "England and Wales" |
| `[CHARITY TAX ID/EIN]` | The charity's tax ID | "EIN: 12-3456789" |
| `[CHARITY EMAIL]` | The charity's contact email | "donations@eff.org" |
| `[INSERT DATE]` | Today's date | "2025-02-22" |
| `[INSERT CLA SIGNING PLATFORM]` | How contributors sign the CLA | "CLA Assistant" or "DocuSign" |
| `[INSERT SIGNING LINK]` | URL to sign the CLA | "https://cla-assistant.io/yourusername/yourproject" |

### Optional Replacements (if applicable):

- `[GitHub Issues]` → Link to your issue tracker
- `[GitHub Discussions / Forum Link]` → Link to community discussions
- `[THIRD_PARTY_LICENSES.md]` → List of third-party dependencies

---

## 📋 STEP 2: DECIDE ON THE CLA MODEL

In the **CONTRIBUTOR_LICENSE_AGREEMENT.md** file, **Section 4.1**, you must choose:

**☐ Option A: License-Only Model**
- Contributors keep copyright
- You get a broad license to dual-license their work
- ✅ **Easier to get contributors to sign**
- ⚠️ **Slightly weaker legal protection** (contributors could theoretically challenge your commercial licensing)

**☐ Option B: Copyright Assignment Model** *(Recommended)*
- Contributors assign copyright to you
- You give them a license to use their contributions
- ✅ **Strongest legal protection** for dual-licensing
- ⚠️ **May deter some contributors** (though most accept it if explained well)

**Action**: Delete the option you're NOT using and clearly mark the one you ARE using.

---

## 📋 STEP 3: SET UP THE COMPLIANCE FOLDER

Create the folder structure for transparency:

```bash
mkdir -p compliance/donation-receipts
mkdir -p compliance/annual-reports
```

Add a placeholder README:

```bash
echo "# Donation Receipts\n\nQuarterly donation receipts will be published here." > compliance/donation-receipts/README.md
```

---

## 📋 STEP 4: VERIFY THE CHARITY

Before launching, confirm:

1. ✅ **The charity is legitimate** (check IRS Tax Exempt Organization Search, Charity Navigator, or equivalent in your country)
2. ✅ **The charity accepts donations** from businesses
3. ✅ **You have their correct legal name** and tax ID
4. ✅ **They can provide receipts** for your donations
5. ✅ **Their mission aligns** with your project's values

---

## 📋 STEP 5: GET LEGAL REVIEW

**⚠️ CRITICAL**: These documents are templates, not legal advice.

You **MUST** have them reviewed by a licensed attorney, especially:

1. **Commercial License** → To ensure the liability disclaimers are enforceable in your jurisdiction
2. **CLA** → To confirm it achieves your ownership goals
3. **Jurisdiction-specific compliance** → Some countries/states have consumer protection laws that may affect your $49 license terms

**Questions to ask your attorney**:
- Are the warranty disclaimers enforceable in [YOUR JURISDICTION]?
- Does the CLA give me sufficient rights to dual-license?
- Do I need additional disclosures for the charitable contribution?
- Are there tax implications I should be aware of?
- Do I need a privacy policy or terms of service for the purchase page?

---

## 📋 STEP 6: SET UP PAYMENT INFRASTRUCTURE

You need a way to sell the $49 license and track sales:

### Recommended Platforms:

| Platform | Pros | Cons |
|----------|------|------|
| **Gumroad** | Easy setup, handles VAT/taxes | 10% + payment fees |
| **Stripe Payment Links** | Low fees (2.9% + $0.30), professional | Requires more setup |
| **Paddle** | Merchant of record (handles VAT for you) | Higher fees (~5%) |
| **LemonSqueezy** | Modern, built for digital products | Relatively new |

### What You Need:

1. ✅ **Payment processor** (Stripe, PayPal, etc.)
2. ✅ **License delivery system** (email the license key/agreement automatically)
3. ✅ **Revenue tracking** (so you can calculate the 30% quarterly)
4. ✅ **Quarterly reminder** (to make donations and publish receipts)

---

## 📋 STEP 7: ADD TO YOUR REPOSITORY

1. **Add the LICENSE file** (AGPLv3):
   ```bash
   curl https://www.gnu.org/licenses/agpl-3.0.txt > LICENSE
   ```

2. **Add the social impact section to your main README.md**:
   - Copy the relevant sections from `SOCIAL_IMPACT_LICENSE.md`
   - Link to the full documents

3. **Link the CLA in your CONTRIBUTING.md**:
   ```markdown
   ## Contributor License Agreement

   All contributors must sign the [Contributor License Agreement](./CONTRIBUTOR_LICENSE_AGREEMENT.md) before their first contribution is merged.
   ```

4. **Set up CLA automation** (optional but recommended):
   - Use [CLA Assistant](https://github.com/cla-assistant/cla-assistant) (free for public repos)
   - Or [CLAHub](https://github.com/clahub/clahub)
   - This will automatically ask contributors to sign the CLA when they open a PR

---

## 📋 STEP 8: LAUNCH CHECKLIST

Before you announce your dual-licensing model:

- ☑️ All placeholders replaced in all 4 documents
- ☑️ CLA model (Option A or B) selected
- ☑️ Legal review completed
- ☑️ Charity verified and contacted
- ☑️ Payment system set up and tested
- ☑️ `/compliance` folder created
- ☑️ README updated with social impact section
- ☑️ CLA signing process working
- ☑️ First quarterly donation date scheduled (e.g., end of Q1)

---

## 📋 STEP 9: QUARTERLY DONATION WORKFLOW

Every 3 months:

1. **Calculate total revenue** from commercial licenses
2. **Calculate 30%** of that revenue
3. **Make the donation** to the charity
4. **Request a receipt** from the charity (official letterhead with their signature)
5. **Create the donation summary** (see template in `TRANSPARENCY_VERIFICATION_PLAN.md`)
6. **Upload both files** to `/compliance/donation-receipts/`
7. **Commit with GPG signature**:
   ```bash
   git add compliance/donation-receipts/2025-Q1-*
   git commit -S -m "chore: publish Q1 2025 donation receipt ($690.90 to [CHARITY])"
   git push
   ```
8. **Announce on social media/blog** (optional but builds trust)

---

## 📋 STEP 10: ANNUAL REVIEW

At the end of each year:

1. ✅ Publish the **annual impact report**
2. ✅ Review and update this plan (if needed)
3. ✅ Consider a **community call** to discuss the year's progress

---

## 🚀 NEXT STEPS

1. **Customize all placeholders** (use find-and-replace in your editor)
2. **Consult an attorney** (budget $500–$2,000 for legal review)
3. **Set up payment infrastructure** (Gumroad/Stripe)
4. **Test the workflow** (make a test purchase, generate a test receipt)
5. **Launch publicly** and start selling!

---

## 💬 QUESTIONS?

If you have questions about implementing this model:

- **Legal**: Consult your attorney
- **Technical**: Stripe/Gumroad support
- **Ethical/Community**: Consider asking in open-source business communities like:
  - [r/opensource](https://reddit.com/r/opensource)
  - [Open Source Initiative discussions](https://opensource.org/community)
  - [Indie Hackers](https://indiehackers.com)

---

## 📚 ADDITIONAL RESOURCES

- **Dual Licensing Explained**: [https://en.wikipedia.org/wiki/Multi-licensing](https://en.wikipedia.org/wiki/Multi-licensing)
- **AGPLv3 FAQ**: [https://www.gnu.org/licenses/gpl-faq.html#AGPLv3](https://www.gnu.org/licenses/gpl-faq.html#AGPLv3)
- **CLA Best Practices**: [https://contributoragreements.org/](https://contributoragreements.org/)
- **Charity Verification (US)**: [https://www.irs.gov/charities-non-profits/tax-exempt-organization-search](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search)

---

**Good luck with your social impact software project!**

---

## DOCUMENT OVERVIEW

Here's what you now have:

1. **SOCIAL_IMPACT_LICENSE.md** → The README section explaining your model to users
2. **COMMERCIAL_LICENSE.md** → The legal agreement purchasers receive with their $49 license
3. **CONTRIBUTOR_LICENSE_AGREEMENT.md** → What contributors sign to enable dual-licensing
4. **TRANSPARENCY_VERIFICATION_PLAN.md** → Your public commitment to proving donations
5. **SOCIAL_IMPACT_LICENSE_IMPLEMENTATION_GUIDE.md** *(this file)* → How to deploy everything

All documents are professionally structured, legally-minded (with strong disclaimers), and ready for customization.
