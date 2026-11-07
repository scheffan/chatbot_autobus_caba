// Textos para la persona: nombres de paradas, cuadras e indicaciones.
import { referenciaCercana } from './red.js';

const TITULOS = /^(GRAL\.?|GENERAL|DR\.?|DOCTOR|PRES\.?|PRESIDENTE|CNEL\.?|CORONEL|ALTE\.?|ALMIRANTE|TTE\.?|TENIENTE|ING\.?|INGENIERO|GOB\.?|GOBERNADOR|MCAL\.?|MARISCAL|CAP\.?|CAPITAN|COMODORO|STA\.?|SANTA|SAN|PJE\.?|PASAJE)$/i;
const MINUSCULAS = new Set(['de', 'del', 'y', 'e', 'a', 'al']);
const ARTICULOS = new Set(['la', 'las', 'los', 'el']);

function tituloPalabra(palabra, i, todas) {
  const p = palabra.toLowerCase();
  if (i > 0 && MINUSCULAS.has(p)) return p;
  if (i > 0 && ARTICULOS.has(p) && todas[i - 1].toLowerCase() === 'de') return p;
  return p.charAt(0).toUpperCase() + p.slice(1);
}

// "AVENIDA EVA PERÓN 1249-1299" -> "Av. Eva Perón 1249"
// "1079 PAZ GRAL. AV." -> "Av. Gral. Paz 1079"
export function nombreDeParada(crudo) {
  let texto = (crudo || '').replace(/\s+/g, ' ').trim();
  let numero = '';
  const alPrincipio = texto.match(/^(\d+)\s+(.*)$/);
  if (alPrincipio) {
    numero = alPrincipio[1];
    texto = alPrincipio[2];
  }
  const alFinal = texto.match(/^(.*?)\s+(\d+)(?:\s*-\s*\d+)?$/);
  if (alFinal) {
    texto = alFinal[1];
    numero = numero || alFinal[2];
  }
  let avenida = false;
  if (/\bAV\.?$/i.test(texto)) {
    avenida = true;
    texto = texto.replace(/\s*\bAV\.?$/i, '');
  }
  if (/^AVENIDA\s+/i.test(texto) || /^AV\.?\s+/i.test(texto)) {
    avenida = true;
    texto = texto.replace(/^(AVENIDA|AV\.?)\s+/i, '');
  }
  // "PAZ GRAL." -> "Gral. Paz", "BROWN ALTE." -> "Alte. Brown"
  const palabras = texto.split(' ');
  const titulos = [];
  while (palabras.length > 1 && TITULOS.test(palabras[palabras.length - 1])) titulos.unshift(palabras.pop());
  const nombre = [...titulos, ...palabras].map((p, i, todas) => tituloPalabra(p, i, todas)).join(' ');
  return `${avenida ? 'Av. ' : ''}${nombre}${numero ? ` ${numero}` : ''}`.trim();
}

// "cerca de el Obelisco" -> "cerca del Obelisco"
export function contraer(texto) {
  return texto.replace(/\bde el\b/g, 'del').replace(/\ba el\b/g, 'al');
}

export function cuadras(metros) {
  if (metros < 60) return 'unos pasos';
  const n = Math.max(1, Math.round(metros / 100));
  return n === 1 ? '1 cuadra' : `${n} cuadras`;
}

export function minutos(m) {
  const n = Math.max(1, Math.round(m));
  return n === 1 ? '1 minuto' : `${n} minutos`;
}

function referencia(red, parada) {
  const p = red.paradas[parada];
  const lugar = referenciaCercana(red, p.lat, p.lon);
  if (!lugar) return '';
  const frase = lugar.dist < 50 ? `, frente a ${lugar.nombre}` : `, cerca de ${lugar.nombre}`;
  return contraer(frase);
}

export function nombreLinea(tramo) {
  return tramo.ramal && tramo.variosRamales ? `${tramo.linea} (ramal ${tramo.ramal})` : tramo.linea;
}

// Arma la lista de pasos de una opción, en criollo.
export function indicaciones(red, opcion, { destino = 'tu destino' } = {}) {
  const pasos = [];
  const tramos = opcion.tramos;
  tramos.forEach((t, idx) => {
    if (t.tipo === 'caminar') {
      if (t.hasta === null) {
        if (t.metros >= 60) pasos.push(`🚶 Caminá ${cuadras(t.metros)} hasta ${destino}.`);
        else pasos.push(contraer(`📍 Llegaste a ${destino}.`));
        return;
      }
      const donde = `${nombreDeParada(red.paradas[t.hasta].nombre)}${referencia(red, t.hasta)}`;
      if (idx === 0) {
        pasos.push(t.metros >= 60 ? `🚶 Caminá ${cuadras(t.metros)} hasta la parada de ${donde}.` : `🚏 Andá a la parada de ${donde}.`);
      } else {
        const misma = tramos[idx - 1].hasta === t.hasta;
        if (misma) pasos.push(`🔁 Cambiá en la misma parada (${donde}).`);
        else if (t.metros < 60) pasos.push(`🔁 Bajate y andá a la parada de ${donde}, a unos pasos.`);
        else pasos.push(`🚶 Bajate y caminá ${cuadras(t.metros)} hasta la parada de ${donde}.`);
      }
      return;
    }
    pasos.push(
      `🚌 Tomá el ${nombreLinea(t)} hacia ${t.haciaEsParada ? nombreDeParada(t.hacia) : t.hacia}. Pasa cada ${t.cada} min aprox.`,
      `⏱️ Viajás ${minutos(t.minutos)} (${t.paradas} paradas) y te bajás en ${nombreDeParada(red.paradas[t.hasta].nombre)}${referencia(red, t.hasta)}.`,
    );
  });
  return pasos;
}

export function resumen(opcion) {
  const lineas = opcion.tramos.filter((t) => t.tipo === 'colectivo').map(nombreLinea);
  const como = lineas.length === 1 ? `el ${lineas[0]}` : `el ${lineas[0]} y después el ${lineas[1]}`;
  return `${como}, unos ${minutos(opcion.total)} en total`;
}
