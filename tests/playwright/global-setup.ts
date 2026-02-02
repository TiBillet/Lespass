import { execSync } from 'child_process';

function generateApiKey() {
  const command = 'docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key';
  const output = execSync(command, { encoding: 'utf8' }).trim();

  if (!output) {
    throw new Error('API key generation returned empty output');
  }

  return output;
}

async function globalSetup() {
  process.env.API_KEY = generateApiKey();
}

export default globalSetup;
