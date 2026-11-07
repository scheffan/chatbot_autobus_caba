// Carga la red (salida de datos/construir_red.py) y arma los índices.
import { Grilla } from './geo.js';

export const RADIO_VECINAS = 250;

export function prepararRed(datos, referencias = []) {
  const paradas = datos.paradas.map(([lat, lon, nombre], i) => ({ i, lat, lon, nombre }));
  const recorridos = datos.recorridos;

  // Para cada parada: qué recorridos pasan y en qué posición.
  const pasan = paradas.map(() => []);
  recorridos.forEach((r, ri) => {
    r.paradas.forEach((p, pos) => pasan[p].push([ri, pos]));
  });

  // Solo nombramos el ramal si la línea tiene más de uno.
  const ramales = new Map();
  for (const r of recorridos) {
    if (!ramales.has(r.linea)) ramales.set(r.linea, new Set());
    ramales.get(r.linea).add(r.ramal);
  }
  for (const r of recorridos) r.variosRamales = ramales.get(r.linea).size > 1;

  const lugares = referencias.map(([lat, lon, nombre, tipo]) => ({ lat, lon, nombre, tipo }));

  const grilla = new Grilla(paradas);
  // Paradas a pocos metros de cada parada, para los trasbordos caminando.
  // Se calculan la primera vez que hacen falta y quedan guardadas.
  const guardadas = new Array(paradas.length);
  const vecinas = (i) => {
    let plano = guardadas[i];
    if (!plano) {
      const p = paradas[i];
      const lista = grilla.cercanos(p.lat, p.lon, RADIO_VECINAS);
      plano = new Float64Array(lista.length * 2);
      lista.forEach((v, k) => { plano[2 * k] = v.i; plano[2 * k + 1] = v.dist; });
      guardadas[i] = plano;
    }
    return plano;
  };

  return {
    paradas,
    vecinas,
    recorridos,
    pasan,
    lugares,
    grilla,
    grillaLugares: new Grilla(lugares),
    fuente: datos.fuente,
  };
}

// Lugar conocido más cercano a un punto (Obelisco, un banco, una plaza…).
export function referenciaCercana(red, lat, lon, radio = 120) {
  const [cerca] = red.grillaLugares.cercanos(lat, lon, radio);
  if (!cerca) return null;
  return { ...red.lugares[cerca.i], dist: cerca.dist };
}

// Busca lugares conocidos por nombre ("obelisco", "plaza de mayo").
export function buscarLugar(red, texto) {
  const buscado = normalizar(texto);
  if (buscado.length < 4) return null;
  let mejor = null;
  for (const lugar of red.lugares) {
    const nombre = normalizar(lugar.nombre);
    if (nombre === buscado) return lugar;
    if (!mejor && nombre.length >= 4 && (nombre.startsWith(buscado) || buscado === nombre.replace(/^(el|la|los|las) /, ''))) {
      mejor = lugar;
    }
  }
  return mejor;
}

export function normalizar(texto) {
  return (texto || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9ñ ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
