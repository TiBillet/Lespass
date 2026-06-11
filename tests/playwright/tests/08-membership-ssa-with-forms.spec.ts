import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Create SSA Membership with Dynamic Form Fields
 * TEST : Créer l'adhésion SSA avec des champs de formulaire dynamiques
 */

async function addFormField(page: Page, fieldData: {
  label: string;
  type: string;
  required: boolean;
  help_text: string;
  order: number;
  options?: string;
}) {
  // Inline Unfold : conteneur #form_fields-group (prefix = related_name 'form_fields'),
  // bouton d'ajout = a.add-row. Le champ 'order' est cache (hide_ordering_field,
  // gere par drag & drop), on ne le remplit pas.
  // / Unfold inline: container #form_fields-group (prefix = related_name 'form_fields'),
  // add button = a.add-row. The 'order' field is hidden (hide_ordering_field,
  // managed by drag & drop), we do not fill it.
  const section = page.locator('#form_fields-group');
  const countBefore = await section.locator('input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])').count();

  await section.locator('a.add-row').first().click();

  const formIndex = countBefore;
  const labelInput = section.locator(`input[name="form_fields-${formIndex}-label"]`);
  await labelInput.waitFor({ state: 'visible', timeout: 5000 });

  console.log(`✓ Adding form field / Ajout du champ : ${fieldData.label}`);

  await labelInput.fill(fieldData.label);
  await section.locator(`select[name="form_fields-${formIndex}-field_type"]`).selectOption(fieldData.type);

  if (fieldData.required) {
    await section.locator(`input[name="form_fields-${formIndex}-required"]`).check();
  }

  await section.locator(`input[name="form_fields-${formIndex}-help_text"], textarea[name="form_fields-${formIndex}-help_text"]`).fill(fieldData.help_text);

  if (fieldData.options) {
    // Les options se saisissent via le champ CSV 'options_csv' (proxy du JSONField).
    // / Options are entered via the 'options_csv' CSV field (JSONField proxy).
    const optionsInput = section.locator(`input[name="form_fields-${formIndex}-options_csv"], textarea[name="form_fields-${formIndex}-options_csv"]`);
    if (await optionsInput.count() > 0) {
      await optionsInput.fill(fieldData.options);
    }
  }
}

test.describe('SSA Membership Creation / Création Adhésion SSA', () => {
  let productExists = false;

  test('Create SSA product with form fields / Créer produit SSA avec questionnaires', async ({ page }) => {
    await test.step('Login / Connexion', async () => { await loginAsAdmin(page); });

    await test.step('Open or Check / Ouvrir ou Vérifier', async () => {
      // L'admin produit a ete refondu en proxys : les adhesions se creent via
      // /admin/BaseBillet/membershipproduct/ (la categorie est fixee par le proxy).
      // / Product admin was split into proxies: memberships are created via
      // the membershipproduct proxy (category is set by the proxy itself).
      await page.goto('/admin/BaseBillet/membershipproduct/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Caisse de sécurité sociale alimentaire' }).first();
      if (await productLink.count() > 0) {
        console.log('✓ SSA product already exists, opening / Produit SSA déjà existant, ouverture');
        productExists = true;
        await productLink.click();
      } else {
        await page.goto('/admin/BaseBillet/membershipproduct/add/');
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Fill info / Remplir les infos', async () => {
      if (productExists) return;
      await page.locator('input[name="name"]').fill('Caisse de sécurité sociale alimentaire');
      await page.locator('input[name="short_description"]').fill('Payez selon vos moyens, recevez selon vos besoins !');
      // Pas de selection de categorie : le proxy MembershipProduct la fixe (champ cache).
      // / No category selection: the MembershipProduct proxy sets it (hidden field).
    });

    await test.step('Initial save / Enregistrement initial', async () => {
      if (productExists) return;
      // We use "Save and continue editing" to stay on the same page
      // On utilise "Enregistrer et continuer les modifications" pour rester sur la page
      const saveAndContinueButton = page.locator('button[name="_continue"], input[name="_continue"]').first();
      if (await saveAndContinueButton.count() > 0) {
        await saveAndContinueButton.click();
      } else {
        await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Add form fields / Ajouter les champs', async () => {
      // Re-open if saved and redirected to list
      // Réouvrir si enregistré et redirigé vers la liste
      if (page.url().endsWith('/product/')) {
        const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Caisse de sécurité sociale alimentaire' }).first();
        await productLink.click();
        await page.waitForLoadState('networkidle');
      }

      // Onglet Unfold de l'inline : ancre #form_fields (activeTab Alpine.js).
      // / Unfold inline tab: #form_fields anchor (Alpine.js activeTab).
      const tab = page.locator('a[href="#form_fields"]').first();
      if (await tab.count() > 0) {
        await tab.click();
        await page.waitForTimeout(1000); // Wait for tab animation
      }

      // Atomic check on first label to avoid duplicates
      // Vérification atomique sur le premier libellé pour éviter les doublons
      const section = page.locator('#form_fields-group');
      const firstLabel = section.locator('input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])').first();
      const count = await firstLabel.count();
      const value = count > 0 ? await firstLabel.inputValue() : "";

      if (count === 0 || value.trim() === "") {
        await addFormField(page, {
          label: 'Pseudonyme',
          type: 'ST',
          required: true,
          help_text: 'Affiché à la communauté.',
          order: 1
        });
      } else {
        console.log(`✓ Form fields already present (found: ${value}) / Champs déjà présents`);
      }
    });

    await test.step('Final save / Enregistrement final', async () => {
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log('✓ SSA Product complete / Produit SSA terminé');
    });
  });
});
