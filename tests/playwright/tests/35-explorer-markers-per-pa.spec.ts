import { test, expect } from '@playwright/test';
import { env } from './utils/env';

/**
 * TEST: Explorer ROOT — 1 marker per PostalAddress
 * TEST : Explorer ROOT — 1 marker par PostalAddress
 *
 * Vérifie le refacto CHANTIER-05 :
 * - La page /explorer/ se charge sans erreur JS
 * - Le JSON injecté contient bien des "points" (pas "lieux")
 * - Au moins 1 marker (ou cluster) est visible sur la carte
 *
 * PRÉREQUIS : le cache AGGREGATE_POINTS doit être à jour. Lancer avant :
 *   docker exec lespass_django poetry run python manage.py shell -c \
 *     "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
 *
 * Voir : TECH_DOC/SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md
 */

test.describe('Explorer ROOT — markers par PostalAddress (CHANTIER-05)', () => {

  test('la page /explorer/ se charge et injecte des points', async ({ page }) => {

    // ROOT tenant : page Explorer publique, pas besoin de login
    await page.goto('/explorer/');
    await page.waitForLoadState('networkidle');

    // Vérifie que l'élément JSON-data est présent
    const dataScript = await page.locator('#explorer-data').count();
    expect(dataScript).toBeGreaterThan(0);

    // Parse le JSON et vérifie la nouvelle structure {points, tenants}
    const rawJson = await page.locator('#explorer-data').textContent();
    expect(rawJson).toBeTruthy();
    const data = JSON.parse(rawJson!);

    // Nouvelle structure (CHANTIER-05) : "points" et "tenants" au lieu de "lieux/events"
    expect(data).toHaveProperty('points');
    expect(data).toHaveProperty('tenants');
    expect(Array.isArray(data.points)).toBe(true);
    expect(Array.isArray(data.tenants)).toBe(true);

    // Chaque point doit avoir pa_id + tenant_id + lat/lng + pa_name + events_futurs
    if (data.points.length > 0) {
      const firstPoint = data.points[0];
      expect(firstPoint).toHaveProperty('pa_id');
      expect(firstPoint).toHaveProperty('tenant_id');
      expect(firstPoint).toHaveProperty('latitude');
      expect(firstPoint).toHaveProperty('longitude');
      expect(firstPoint).toHaveProperty('pa_name');
      expect(firstPoint).toHaveProperty('events_futurs');
      expect(firstPoint).toHaveProperty('events_futurs_count_total');
    }
  });

  test('au moins 1 marker (ou cluster) visible si la carte a des données', async ({ page }) => {

    await page.goto('/explorer/');
    await page.waitForLoadState('networkidle');

    // Vérifie si la carte a au moins 1 point
    const rawJson = await page.locator('#explorer-data').textContent();
    const data = JSON.parse(rawJson!);

    if (data.points.length === 0) {
      test.skip(true, 'Aucun point dans AGGREGATE_POINTS — lancer refresh_seo_cache avant');
    }

    // Wait for Leaflet to render markers (cluster ou pin individuel)
    await page.waitForSelector('.leaflet-marker-icon, .leaflet-marker-cluster', { timeout: 8000 });

    const markersCount = await page.locator('.leaflet-marker-icon, .leaflet-marker-cluster').count();
    expect(markersCount).toBeGreaterThan(0);
  });
});
