import { execSync } from 'child_process';

/**
 * DATABASE VERIFICATION HELPER
 * AIDE À LA VÉRIFICATION EN BASE DE DONNÉES
 * 
 * This helper calls the Django management command via Docker to verify test results.
 * Cet helper appelle la commande de gestion Django via Docker pour vérifier les résultats des tests.
 */
export async function verifyDbData(params: {
    type: 'reservation' | 'membership' | 'tokens';
    email: string;
    event?: string;
    product?: string;
}) {
    const { type, email, event, product } = params;
    
    let command = `docker exec -w /DjangoFiles -e PYTHONPATH=/DjangoFiles lespass_django poetry run python tests/scripts/verify_test_data.py --type ${type} --email ${email}`;
    
    if (event) command += ` --event "${event}"`;
    if (product) command += ` --product "${product}"`;

    console.log(`[DB Verify] Executing: ${command}`);
    
    try {
        const output = execSync(command).toString();
        const result = JSON.parse(output);
        
        if (result.status === 'success') {
            console.log(`✓ DB verification successful for ${email} (${type})`);
            return result;
        } else {
            console.error(`✗ DB verification failed: ${result.message}`);
            return null;
        }
    } catch (error) {
        console.error(`✗ Error executing DB verification: ${error.message}`);
        return null;
    }
}
