import { APIRequestContext } from '@playwright/test';
import { env } from './env';

/**
 * API HELPERS FOR E2E SETUP
 * HELPERS API POUR SETUP E2E
 */

function slugifyName(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function slugFromEventUrl(url: string | undefined) {
  if (!url) return undefined;
  const parts = url.split('/').filter(Boolean);
  const eventIndex = parts.findIndex(part => part === 'event');
  if (eventIndex === -1) return undefined;
  return parts[eventIndex + 1];
}

export async function createEvent(params: {
  request: APIRequestContext;
  name: string;
  startDate: string;
  maxPerUser?: number;
  optionsRadio?: string[];
  optionsCheckbox?: string[];
}) {
  const { request, name, startDate, maxPerUser, optionsRadio, optionsCheckbox } = params;

  const additionalProperty = [];
  if (optionsRadio && optionsRadio.length > 0) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'optionsRadio',
      value: optionsRadio,
    });
  }
  if (optionsCheckbox && optionsCheckbox.length > 0) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'optionsCheckbox',
      value: optionsCheckbox,
    });
  }

  const eventResponse = await request.post(`${env.BASE_URL}/api/v2/events/`, {
    headers: {
      Authorization: `Api-Key ${env.API_KEY}`,
      'Content-Type': 'application/json',
    },
    data: {
      '@context': 'https://schema.org',
      '@type': 'Event',
      name,
      startDate,
      offers: maxPerUser ? { eligibleQuantity: { maxValue: maxPerUser } } : undefined,
      additionalProperty: additionalProperty.length > 0 ? additionalProperty : undefined,
    },
  });

  let eventData: any = null;
  let rawText = '';
  try {
    eventData = await eventResponse.json();
  } catch (error) {
    rawText = await eventResponse.text();
  }
  const eventSlug = slugFromEventUrl(eventData?.url) || slugifyName(name);

  return {
    ok: eventResponse.ok(),
    status: eventResponse.status(),
    errorText: rawText,
    data: eventData,
    slug: eventSlug,
    uuid: eventData?.identifier,
  };
}

export async function createProduct(params: {
  request: APIRequestContext;
  name: string;
  description?: string;
  category?: string;
  eventUuid?: string;
  productMaxPerUser?: number;
  offers: Array<{
    name: string;
    price: string;
    freePrice?: boolean;
    stock?: number;
    maxPerUser?: number;
    membershipRequiredProduct?: string;
    recurringPayment?: boolean;
    subscriptionType?: string;
  }>;
  formFields?: Array<{
    label: string;
    fieldType: string;
    required?: boolean;
    options?: string[];
    order?: number;
  }>;
}) {
  const { request, name, description, category, eventUuid, offers, formFields } = params;

  const additionalProperty = [];
  if (formFields && formFields.length > 0) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'formFields',
      value: formFields,
    });
  }
  if (params.productMaxPerUser !== undefined) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'maxPerUser',
      value: params.productMaxPerUser,
    });
  }

  const productResponse = await request.post(`${env.BASE_URL}/api/v2/products/`, {
    headers: {
      Authorization: `Api-Key ${env.API_KEY}`,
      'Content-Type': 'application/json',
    },
    data: {
      '@context': 'https://schema.org',
      '@type': 'Product',
      name,
      description: description ?? '',
      category: category ?? 'Ticket booking',
      isRelatedTo: eventUuid ? { '@type': 'Event', identifier: eventUuid } : undefined,
      offers: offers.map(offer => ({
        '@type': 'Offer',
        name: offer.name,
        price: offer.price,
        priceCurrency: 'EUR',
        freePrice: offer.freePrice,
        stock: offer.stock,
        maxPerUser: offer.maxPerUser,
        membershipRequiredProduct: offer.membershipRequiredProduct,
        additionalProperty: [
          offer.recurringPayment !== undefined ? {
            '@type': 'PropertyValue',
            name: 'recurringPayment',
            value: offer.recurringPayment,
          } : null,
          offer.subscriptionType ? {
            '@type': 'PropertyValue',
            name: 'subscriptionType',
            value: offer.subscriptionType,
          } : null,
        ].filter(Boolean),
      })),
      additionalProperty: additionalProperty.length > 0 ? additionalProperty : undefined,
    },
  });

  let productData: any = null;
  let rawText = '';
  try {
    productData = await productResponse.json();
  } catch (error) {
    rawText = await productResponse.text();
  }

  return {
    ok: productResponse.ok(),
    status: productResponse.status(),
    errorText: rawText,
    data: productData,
    uuid: productData?.identifier,
    offers: productData?.offers,
  };
}

export async function createReservationApi(params: {
  request: APIRequestContext;
  eventUuid: string;
  email: string;
  tickets: Array<{
    priceUuid: string;
    qty?: number;
    customAmount?: string;
  }>;
  options?: string[];
  customForm?: Record<string, string>;
  confirmed?: boolean;
  promotionalCode?: string;
}) {
  const additionalProperty = [];
  if (params.options && params.options.length > 0) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'options',
      value: params.options,
    });
  }
  if (params.customForm) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'customForm',
      value: params.customForm,
    });
  }
  if (params.confirmed !== undefined) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'confirmed',
      value: params.confirmed,
    });
  }
  if (params.promotionalCode) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'promotionalCode',
      value: params.promotionalCode,
    });
  }

  const response = await params.request.post(`${env.BASE_URL}/api/v2/reservations/`, {
    headers: {
      Authorization: `Api-Key ${env.API_KEY}`,
      'Content-Type': 'application/json',
    },
    data: {
      '@context': 'https://schema.org',
      '@type': 'Reservation',
      reservationFor: {
        '@type': 'Event',
        identifier: params.eventUuid,
      },
      underName: {
        '@type': 'Person',
        email: params.email,
      },
      reservedTicket: params.tickets.map(ticket => ({
        '@type': 'Ticket',
        identifier: ticket.priceUuid,
        ticketQuantity: ticket.qty ?? 1,
        price: ticket.customAmount,
      })),
      additionalProperty: additionalProperty.length > 0 ? additionalProperty : undefined,
    },
  });

  const data = await response.json();
  return { ok: response.ok(), data };
}

export async function createMembershipApi(params: {
  request: APIRequestContext;
  priceUuid: string;
  email: string;
  firstName?: string;
  lastName?: string;
  paymentMode?: 'FREE' | 'STRIPE';
  customAmount?: string;
  options?: string[];
  customForm?: Record<string, string>;
  validUntil?: string;
  status?: string;
  stripeSubscriptionId?: string;
}) {
  const additionalProperty = [];
  additionalProperty.push({
    '@type': 'PropertyValue',
    name: 'paymentMode',
    value: params.paymentMode ?? 'FREE',
  });
  if (params.customAmount) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'customAmount',
      value: params.customAmount,
    });
  }
  if (params.options && params.options.length > 0) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'options',
      value: params.options,
    });
  }
  if (params.customForm) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'customForm',
      value: params.customForm,
    });
  }
  if (params.status) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'status',
      value: params.status,
    });
  }
  if (params.stripeSubscriptionId) {
    additionalProperty.push({
      '@type': 'PropertyValue',
      name: 'stripeSubscriptionId',
      value: params.stripeSubscriptionId,
    });
  }

  const response = await params.request.post(`${env.BASE_URL}/api/v2/memberships/`, {
    headers: {
      Authorization: `Api-Key ${env.API_KEY}`,
      'Content-Type': 'application/json',
    },
    data: {
      '@context': 'https://schema.org',
      '@type': 'ProgramMembership',
      member: {
        '@type': 'Person',
        email: params.email,
        givenName: params.firstName ?? 'API',
        familyName: params.lastName ?? 'Member',
      },
      membershipPlan: {
        '@type': 'Offer',
        identifier: params.priceUuid,
      },
      validUntil: params.validUntil,
      additionalProperty,
    },
  });

  let data: any = null;
  let rawText = '';
  try {
    data = await response.json();
  } catch (error) {
    rawText = await response.text();
  }
  if (!response.ok()) {
    // Keep a visible clue in test output when API setup fails
    console.warn('createMembershipApi failed', {
      status: response.status(),
      data,
      errorText: rawText,
    });
  }
  return {
    ok: response.ok(),
    status: response.status(),
    errorText: rawText,
    data,
  };
}
