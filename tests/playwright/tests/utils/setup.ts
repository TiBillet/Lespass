import { execSync } from 'child_process';

/**
 * SETUP HELPER FOR TEST DATA (DB SIDE)
 * AIDE SETUP POUR LES DONNEES DE TEST (COTE DB)
 */
function runSetupCommand(args: string[]) {
  const command = [
    'docker exec -w /DjangoFiles -e PYTHONPATH=/DjangoFiles',
    'lespass_django',
    'poetry run python tests/scripts/setup_test_data.py',
    ...args,
  ].join(' ');

  console.log(`[DB Setup] Executing: ${command}`);

  try {
    const output = execSync(command).toString();
    const result = JSON.parse(output);
    if (result.status !== 'success') {
      console.error(`[DB Setup] Failed: ${JSON.stringify(result)}`);
    }
    return result;
  } catch (error: any) {
    console.error(`[DB Setup] Error: ${error.message}`);
    return { status: 'error', message: error.message };
  }
}

export function createReservationInDb(params: {
  event: string;
  product: string;
  price?: string;
  email: string;
  qty?: number;
  customAmount?: number;
}) {
  const args = [
    '--action create_reservation',
    `--event "${params.event}"`,
    `--product "${params.product}"`,
    `--email "${params.email}"`,
    `--qty "${params.qty ?? 1}"`,
  ];

  if (params.price) args.push(`--price "${params.price}"`);
  if (params.customAmount !== undefined) args.push(`--custom-amount "${params.customAmount}"`);

  return runSetupCommand(args);
}

export function createTicketsInDb(params: {
  event: string;
  product: string;
  price?: string;
  email: string;
  qty?: number;
}) {
  const args = [
    '--action create_ticket',
    `--event "${params.event}"`,
    `--product "${params.product}"`,
    `--email "${params.email}"`,
    `--qty "${params.qty ?? 1}"`,
  ];

  if (params.price) args.push(`--price "${params.price}"`);

  return runSetupCommand(args);
}

export function createMembershipInDb(params: {
  product: string;
  price?: string;
  email: string;
  deadlineDays?: number;
  status?: string;
  stripeSubscriptionId?: string;
}) {
  const args = [
    '--action create_membership',
    `--product "${params.product}"`,
    `--email "${params.email}"`,
  ];

  if (params.price) args.push(`--price "${params.price}"`);
  if (params.deadlineDays !== undefined) args.push(`--deadline-days "${params.deadlineDays}"`);
  if (params.status) args.push(`--status "${params.status}"`);
  if (params.stripeSubscriptionId) {
    args.push(`--stripe-subscription-id "${params.stripeSubscriptionId}"`);
  }

  return runSetupCommand(args);
}

export function createPromotionalCodeInDb(params: {
  product: string;
  codeName: string;
  discountRate?: number;
}) {
  const args = [
    '--action create_promotional_code',
    `--product "${params.product}"`,
    `--code-name "${params.codeName}"`,
  ];

  if (params.discountRate !== undefined) {
    args.push(`--discount-rate "${params.discountRate}"`);
  }

  return runSetupCommand(args);
}

export function linkPriceToMembershipInDb(params: {
  product: string;
  price?: string;
  membershipProduct: string;
}) {
  const args = [
    '--action link_price_to_membership',
    `--product "${params.product}"`,
    `--membership-product "${params.membershipProduct}"`,
  ];

  if (params.price) args.push(`--price "${params.price}"`);

  return runSetupCommand(args);
}

export function setProductMaxPerUserInDb(params: {
  product: string;
  maxPerUser: number;
}) {
  const args = [
    '--action set_product_max_per_user',
    `--product "${params.product}"`,
    `--max-per-user "${params.maxPerUser}"`,
  ];

  return runSetupCommand(args);
}

export function setPriceRecurringInDb(params: {
  product: string;
  price?: string;
  subscriptionType?: string;
  recurringPayment?: boolean;
}) {
  const args = [
    '--action set_price_recurring',
    `--product "${params.product}"`,
  ];

  if (params.price) args.push(`--price "${params.price}"`);
  if (params.subscriptionType) args.push(`--subscription-type "${params.subscriptionType}"`);
  if (params.recurringPayment !== undefined) {
    args.push(`--recurring-payment "${params.recurringPayment ? 1 : 0}"`);
  }

  return runSetupCommand(args);
}
