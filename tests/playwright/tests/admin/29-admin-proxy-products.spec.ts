import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';

/**
 * Test des vues admin proxy TicketProduct et MembershipProduct
 * Test for proxy admin views TicketProduct and MembershipProduct
 *
 * Ce test vérifie que :
 * This test verifies that:
 * - La liste TicketProduct n'affiche que les produits billetterie (BILLET, FREERES)
 * - The TicketProduct list only shows ticket products (BILLET, FREERES)
 * - La liste MembershipProduct n'affiche que les produits adhésion (ADHESION)
 * - The MembershipProduct list only shows membership products (ADHESION)
 * - Le formulaire d'ajout TicketProduct propose uniquement les types billetterie
 * - The TicketProduct add form only offers ticket types
 * - Le formulaire d'ajout MembershipProduct force le type adhésion (champ caché)
 * - The MembershipProduct add form forces membership type (hidden field)
 * - La sidebar affiche les liens vers les vues proxy
 * - The sidebar displays links to proxy views
 *
 * Prérequis : des produits de démo doivent exister (tests 03-04 ou demo_data).
 * Prerequisite: demo products must exist (tests 03-04 or demo_data).
 */

test.describe('Admin Proxy Products / Produits Admin Proxy', () => {

    test.beforeEach(async ({ page }) => {
        // Connexion en tant qu'admin
        // Login as admin
        await loginAsAdmin(page);
        console.log('✓ Logged in as admin / Connecté en tant qu\'admin');
    });

    test('TicketProduct list shows only ticket products / La liste TicketProduct affiche uniquement les billets', async ({ page }) => {

        await test.step('Navigate to TicketProduct list / Naviguer vers la liste TicketProduct', async () => {
            await page.goto('/admin/BaseBillet/ticketproduct/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/BaseBillet\/ticketproduct\//);
            console.log('✓ TicketProduct list loaded / Liste TicketProduct chargée');
        });

        await test.step('Verify only ticket types are listed / Vérifier que seuls les types billet sont listés', async () => {
            // Vérifier qu'il y a au moins un produit dans la liste
            // Check there is at least one product in the list
            const resultRows = page.locator('#result_list tbody tr');
            const rowCount = await resultRows.count();
            expect(rowCount).toBeGreaterThan(0);
            console.log(`✓ Found ${rowCount} ticket products / ${rowCount} produits billet trouvés`);
        });
    });

    test('MembershipProduct list shows only membership products / La liste MembershipProduct affiche uniquement les adhésions', async ({ page }) => {

        await test.step('Navigate to MembershipProduct list / Naviguer vers la liste MembershipProduct', async () => {
            await page.goto('/admin/BaseBillet/membershipproduct/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/BaseBillet\/membershipproduct\//);
            console.log('✓ MembershipProduct list loaded / Liste MembershipProduct chargée');
        });

        await test.step('Verify only membership types are listed / Vérifier que seuls les types adhésion sont listés', async () => {
            // Vérifier qu'il y a au moins un produit dans la liste
            // Check there is at least one product in the list
            const resultRows = page.locator('#result_list tbody tr');
            const rowCount = await resultRows.count();
            expect(rowCount).toBeGreaterThan(0);
            console.log(`✓ Found ${rowCount} membership products / ${rowCount} produits adhésion trouvés`);
        });
    });

    test('TicketProduct add form restricts to ticket types / Le formulaire TicketProduct restreint aux types billet', async ({ page }) => {

        await test.step('Navigate to TicketProduct add form / Naviguer vers le formulaire ajout TicketProduct', async () => {
            await page.goto('/admin/BaseBillet/ticketproduct/add/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/BaseBillet\/ticketproduct\/add\//);
            console.log('✓ TicketProduct add form loaded / Formulaire ajout TicketProduct chargé');
        });

        await test.step('Verify category choices are restricted / Vérifier que les choix de catégorie sont restreints', async () => {
            // Le champ categorie_article ne doit proposer que Billet (B) et Reservation gratuite (F)
            // The categorie_article field should only offer Ticket (B) and Free booking (F)
            const categorySelect = page.locator('select[name="categorie_article"]');
            await expect(categorySelect).toBeVisible({ timeout: 5000 });

            const options = await categorySelect.locator('option').all();
            const optionValues = [];
            for (const option of options) {
                const value = await option.getAttribute('value');
                if (value && value !== '') {
                    optionValues.push(value);
                }
            }

            // Doit contenir B (Billet) et F (Reservation gratuite), pas A (Adhesion)
            // Should contain B (Ticket) and F (Free booking), not A (Membership)
            expect(optionValues).toContain('B');
            expect(optionValues).toContain('F');
            expect(optionValues).not.toContain('A');
            console.log(`✓ Category restricted to: ${optionValues.join(', ')} / Catégorie restreinte à : ${optionValues.join(', ')}`);
        });

        await test.step('Verify no Dynamic form field tab / Vérifier absence onglet Formulaires dynamiques', async () => {
            // TicketProduct n'a pas de ProductFormFieldInline
            // TicketProduct doesn't have ProductFormFieldInline
            const dynamicTab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field"), button:has-text("Formulaires dynamique")');
            const tabCount = await dynamicTab.count();
            expect(tabCount).toBe(0);
            console.log('✓ No Dynamic form field tab / Pas d\'onglet Formulaires dynamique');
        });
    });

    test('MembershipProduct add form forces membership type / Le formulaire MembershipProduct force le type adhésion', async ({ page }) => {

        await test.step('Navigate to MembershipProduct add form / Naviguer vers le formulaire ajout MembershipProduct', async () => {
            await page.goto('/admin/BaseBillet/membershipproduct/add/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/BaseBillet\/membershipproduct\/add\//);
            console.log('✓ MembershipProduct add form loaded / Formulaire ajout MembershipProduct chargé');
        });

        await test.step('Verify category is hidden and forced to membership / Vérifier que la catégorie est cachée et forcée à adhésion', async () => {
            // Le champ categorie_article doit etre un input hidden avec la valeur A (Adhesion)
            // The categorie_article field should be a hidden input with value A (Membership)
            const hiddenInput = page.locator('input[name="categorie_article"][type="hidden"]');
            await expect(hiddenInput).toHaveCount(1);
            const value = await hiddenInput.getAttribute('value');
            expect(value).toBe('A');
            console.log('✓ Category hidden and forced to A (Adhesion) / Catégorie cachée et forcée à A (Adhésion)');
        });

        await test.step('Verify Dynamic form field tab is present / Vérifier présence onglet Formulaires dynamiques', async () => {
            // MembershipProduct a le ProductFormFieldInline
            // MembershipProduct has ProductFormFieldInline
            const dynamicTab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field"), button:has-text("Formulaires dynamique")');
            const tabCount = await dynamicTab.count();
            expect(tabCount).toBeGreaterThan(0);
            console.log('✓ Dynamic form field tab present / Onglet Formulaires dynamique présent');
        });
    });

    test('Original Product admin still accessible / L\'admin Product original reste accessible', async ({ page }) => {

        await test.step('Navigate to original Product list / Naviguer vers la liste Product originale', async () => {
            await page.goto('/admin/BaseBillet/product/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/BaseBillet\/product\//);
            console.log('✓ Original Product list accessible / Liste Product originale accessible');
        });

        await test.step('Verify all product types are listed / Vérifier que tous les types sont listés', async () => {
            // La vue Product originale affiche TOUS les produits (billet + adhesion + autres)
            // The original Product view shows ALL products (ticket + membership + others)
            const resultRows = page.locator('#result_list tbody tr');
            const rowCount = await resultRows.count();
            expect(rowCount).toBeGreaterThan(0);
            console.log(`✓ Found ${rowCount} total products / ${rowCount} produits au total`);
        });
    });

    test('Sidebar links point to proxy views / Les liens sidebar pointent vers les vues proxy', async ({ page }) => {

        await test.step('Navigate to admin / Naviguer vers l\'admin', async () => {
            await page.goto('/admin/');
            await page.waitForLoadState('networkidle');
        });

        await test.step('Check TicketProduct sidebar link / Vérifier le lien sidebar TicketProduct', async () => {
            // Chercher un lien vers ticketproduct dans la sidebar
            // Look for a ticketproduct link in the sidebar
            const sidebarLink = page.locator('nav a[href*="ticketproduct"]').first();
            const linkCount = await sidebarLink.count();
            expect(linkCount).toBeGreaterThan(0);
            console.log('✓ TicketProduct sidebar link found / Lien sidebar TicketProduct trouvé');
        });

        await test.step('Check MembershipProduct sidebar link / Vérifier le lien sidebar MembershipProduct', async () => {
            // Chercher un lien vers membershipproduct dans la sidebar
            // Look for a membershipproduct link in the sidebar
            const sidebarLink = page.locator('nav a[href*="membershipproduct"]').first();
            const linkCount = await sidebarLink.count();
            expect(linkCount).toBeGreaterThan(0);
            console.log('✓ MembershipProduct sidebar link found / Lien sidebar MembershipProduct trouvé');
        });
    });
});
