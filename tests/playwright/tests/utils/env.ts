/**
 * Environment variables helper
 * Provides type-safe access to environment variables loaded from .env file
 */

export const env = {
  /**
   * Admin email address
   */
  get ADMIN_EMAIL(): string {
    const email = process.env.ADMIN_EMAIL;
    if (!email) {
      throw new Error('ADMIN_EMAIL environment variable is not set');
    }
    return email;
  },

  /**
   * Domain name (without subdomain)
   */
  get DOMAIN(): string {
    const domain = process.env.DOMAIN;
    if (!domain) {
      throw new Error('DOMAIN environment variable is not set');
    }
    return domain;
  },

  /**
   * Subdomain for the first tenant
   */
  get SUB(): string {
    const sub = process.env.SUB;
    if (!sub) {
      throw new Error('SUB environment variable is not set');
    }
    return sub;
  },

  /**
   * Full base URL for the first tenant
   */
  get BASE_URL(): string {
    return `https://${this.SUB}.${this.DOMAIN}`;
  },

  /**
   * Stripe test mode flag
   */
  get STRIPE_TEST(): boolean {
    return process.env.STRIPE_TEST === '1';
  },

  /**
   * Test mode flag
   */
  get TEST(): boolean {
    return process.env.TEST === '1';
  },

  /**
   * Debug mode flag
   */
  get DEBUG(): boolean {
    return process.env.DEBUG === '1';
  },
};
