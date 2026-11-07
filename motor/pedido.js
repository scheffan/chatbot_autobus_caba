// Entiende pedidos como "quiero ir de Corrientes 800 a Plaza Italia".

const PATRONES = [
  /(?:^|\b)(?:de|del|desde)\s+(.+?)\s+(?:a|al|hasta|hacia|para)\s+(.+)$/i,
  /(?:^|\b)(?:a|al|hasta|hacia|para)\s+(.+?)\s+(?:de|del|desde)\s+(.+)$/i,
  /^(.+?)\s*(?:->|→|=>|➡️?)\s*(.+)$/,
];

function limpiar(texto) {
  return texto
    .replace(/[¿?¡!.]+$/g, '')
    .replace(/^\s*(?:la|el)\s+(?=calle|avenida|av\.?)/i, '')
    .replace(/^calle\s+/i, '')
    .trim();
}

export function entenderPedido(texto) {
  let t = (texto || '').replace(/\s+/g, ' ').trim();
  t = t.replace(/^(hola[,!]?\s*)?/i, '');
  t = t.replace(/^(quiero|quisiera|necesito|tengo que|como|cómo)\s+(ir|llegar|viajar|voy|llego|hago para ir)\s*/i, '');
  t = t.replace(/^(ir|llegar|viajar)\s+/i, '');
  t = t.replace(/^(como|cómo)\s+(llego|voy)\s*/i, '');

  for (const [n, patron] of PATRONES.entries()) {
    const m = t.match(patron);
    if (!m) continue;
    const [uno, dos] = [limpiar(m[1]), limpiar(m[2])];
    if (!uno || !dos) continue;
    return n === 1 ? { origen: dos, destino: uno } : { origen: uno, destino: dos };
  }
  return null;
}
