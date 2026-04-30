import net from "net"

export function checkPrinter(host, port = 9100, timeout = 2000) {
    return new Promise((resolve) => {
        const socket = new net.Socket()
        let isAlive = 'disable'

        socket.setTimeout(timeout)

        socket.on('connect', () => {
            isAlive = 'available'
            socket.destroy()
        });

        socket.on('error', () => {
            isAlive = 'disable'
        });

        socket.on('timeout', () => {
            isAlive = 'disable'
            socket.destroy()
        });

        socket.on('close', () => {
            resolve(isAlive)
        });

        socket.connect(port, host)
    });
}


export function print(host, content, port = 9100) {
    const client = new net.Socket();

    client.connect(port, host, () => {
        console.log('Connecté à l’imprimante');

        client.write(content);

        // saut de 8 ligne + commande coupe papier (ESC/POS)
        client.write('\n\n\n\n\n\n\n\n')
        client.write(Buffer.from([0x1D, 0x56, 0x00]));

        client.end();
    });

    client.on('error', (err) => {
        console.error('Erreur impression:', err.message);
    });

    client.on('close', () => {
        console.log('Connexion fermée');
    });
}


/*
// Exemple
checkPrinter('192.168.1.50', 9100).then((ok) => {
  console.log(ok ? 'Imprimante OK' : 'Imprimante non joignable');
});
*/