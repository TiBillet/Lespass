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
  const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
  const addButton = section.locator('a:has-text("Add another")').first();
  
  await addButton.click();
  
  // Wait for the new row to appear and be stable
  const lastRow = section.locator('tr.form-row:not(.empty-form)').last();
  await lastRow.waitFor({ state: 'visible', timeout: 5000 });
  
  console.log(`✓ Adding form field / Ajout du champ : ${fieldData.label}`);
  
  await lastRow.locator('input[name*="-label"]').fill(fieldData.label);
  await lastRow.locator('select[name*="-field_type"]').selectOption(fieldData.type);
  
  if (fieldData.required) { 
    await lastRow.locator('input[name*="-required"]').check(); 
  }
  
  await lastRow.locator('input[name*="-help_text"], textarea[name*="-help_text"]').fill(fieldData.help_text);
  
  // Use force:true to avoid visibility/scroll issues if needed
  await lastRow.locator('input[name*="-order"]').fill(fieldData.order.toString(), { force: true });
  
  if (fieldData.options) {
    const optionsTextarea = lastRow.locator('textarea[name*="-options"]');
    if (await optionsTextarea.count() > 0) { 
      await optionsTextarea.fill(fieldData.options); 
    }
  }
}

test.describe('SSA Membership Creation / Création Adhésion SSA', () => {
  let productExists = false;

  test('Create SSA product with form fields / Créer produit SSA avec questionnaires', async ({ page }) => {
    await test.step('Login / Connexion', async () => { await loginAsAdmin(page); });

    await test.step('Open or Check / Ouvrir ou Vérifier', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Caisse de sécurité sociale alimentaire' }).first();
      if (await productLink.count() > 0) {
        console.log('✓ SSA product already exists, opening / Produit SSA déjà existant, ouverture');
        productExists = true;
        await productLink.click();
      } else {
        await page.goto('/admin/BaseBillet/product/add/');
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Fill info / Remplir les infos', async () => {
      if (productExists) return;
      await page.locator('input[name="name"]').fill('Caisse de sécurité sociale alimentaire');
      await page.locator('input[name="short_description"]').fill('Payez selon vos moyens, recevez selon vos besoins !');
      await page.locator('select[name="categorie_article"]').selectOption('A');
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

      const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
      if (await tab.count() > 0) {
        await tab.click();
        await page.waitForTimeout(1000); // Wait for tab animation
      }
      
      // Atomic check on first label to avoid duplicates
      // Vérification atomique sur le premier libellé pour éviter les doublons
      const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
      const firstLabel = section.locator('input[name*="-label"]').first();
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
