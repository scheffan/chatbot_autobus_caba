// Convierte "Corrientes 800", "Corrientes y Callao" u "Obelisco" en coordenadas.
//
// 1) Lugares conocidos de OpenStreetMap que ya tenemos cargados.
// 2) El normalizador de direcciones de la Ciudad (USIG), que entiende
//    alturas e intersecciones de CABA.
// 3) Nominatim (OpenStreetMap) para el resto del AMBA.
// 4) Si nada encontró la dirección, prueba corregir el nombre de la calle
//    ("Corientes 800" -> "Corrientes 800") con las calles de la red.
import { buscarLugar, normalizar } from './red.js';
import { nombreDeParada } from './textos.js';

const USIG = 'https://servicios.usig.buenosaires.gob.ar/normalizar/';
const NOMINATIM = 'https://nominatim.openstreetmap.org/search';
const CAJA_AMBA = '-58.75,-34.40,-58.20,-34.95';

async function porUsig(texto, pedir) {
  const url = `${USIG}?direccion=${encodeURIComponent(texto)}&geocodificar=TRUE&srid=4326&maxOptions=1`;
  const respuesta = await pedir(url);
  if (!respuesta.ok) return null;
  const datos = await respuesta.json();
  const d = datos?.direccionesNormalizadas?.[0];
  const c = d?.coordenadas;
  if (!c || c.x === undefined) return null;
  // Mostramos la dirección como la escribió la persona, no "CORRIENTES AV. 800, CABA".
  return { lat: Number(c.y), lon: Number(c.x), nombre: texto, fuente: 'usig' };
}

function zonaDe(direccion = {}) {
  return direccion.suburb || direccion.neighbourhood || direccion.city_district
    || direccion.town || direccion.city || direccion.county || '';
}

async function porNominatim(texto, pedir) {
  const consulta = /buenos aires|caba|argentina/i.test(texto) ? texto : `${texto}, Buenos Aires`;
  const url = `${NOMINATIM}?format=json&limit=1&addressdetails=1&countrycodes=ar&bounded=1&viewbox=${CAJA_AMBA}&q=${encodeURIComponent(consulta)}`;
  const respuesta = await pedir(url, { headers: { 'Accept-Language': 'es' } });
  if (!respuesta.ok) return null;
  const [d] = await respuesta.json();
  if (!d) return null;
  const resultado = { lat: Number(d.lat), lon: Number(d.lon), nombre: texto, fuente: 'nominatim' };
  // Una calle entera sin altura ni esquina no es un destino: "Mar del Plata" puede ser
  // la ciudad (fuera del AMBA) o una calle de Floresta. Mejor preguntar que inventar el viaje.
  if (d.class === 'highway' && !/\d/.test(texto) && !/\s(y|e)\s/i.test(texto)) {
    return { ...resultado, ambiguo: 'calle', zona: zonaDe(d.address) };
  }
  return resultado;
}

// --- Corrección de errores de tipeo en el nombre de la calle ---------------

export function distanciaEdicion(a, b) {
  if (a === b) return 0;
  let anterior = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const actual = [i];
    for (let j = 1; j <= b.length; j++) {
      actual[j] = Math.min(anterior[j] + 1, actual[j - 1] + 1, anterior[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    anterior = actual;
  }
  return anterior[b.length];
}

// Nombres de calles de la red, sacados de los nombres de las paradas ("1000 RIVADAVIA AV." -> "Rivadavia").
function callesDeLaRed(red) {
  if (!red.calles) {
    const calles = new Map();
    for (const p of red.paradas) {
      const nombre = nombreDeParada(p.nombre).replace(/\s+\d+$/, '').replace(/^Av\. /, '');
      const clave = normalizar(nombre);
      if (clave.length >= 4 && !calles.has(clave)) calles.set(clave, nombre);
    }
    red.calles = calles;
  }
  return red.calles;
}

function corregirNombre(red, nombre) {
  const buscado = normalizar(nombre);
  if (buscado.length < 4) return null;
  const calles = callesDeLaRed(red);
  if (calles.has(buscado)) return null; // está bien escrito: el problema es otro
  const tolerancia = buscado.length <= 6 ? 1 : 2;
  let mejor = null;
  let empate = false;
  for (const [clave, original] of calles) {
    if (Math.abs(clave.length - buscado.length) > tolerancia) continue;
    const d = distanciaEdicion(buscado, clave);
    if (d > tolerancia) continue;
    if (!mejor || d < mejor.d) { mejor = { d, original }; empate = false; } else if (d === mejor.d && original !== mejor.original) empate = true;
  }
  return mejor && !empate ? mejor.original : null;
}

// "Corientes 800" -> "Corrientes 800"; "Corientes y Calao" -> "Corrientes y Callao".
export function corregirDireccion(red, texto) {
  if (!red?.paradas) return null;
  const conAltura = texto.match(/^(.+?)\s+(\d{1,5})$/);
  if (conAltura) {
    const calle = corregirNombre(red, conAltura[1]);
    return calle ? `${calle} ${conAltura[2]}` : null;
  }
  const esquina = texto.match(/^(.+?)\s+y\s+(.+)$/i);
  if (esquina) {
    const [uno, dos] = [corregirNombre(red, esquina[1]), corregirNombre(red, esquina[2])];
    if (!uno && !dos) return null;
    return `${uno || esquina[1]} y ${dos || esquina[2]}`;
  }
  return null;
}

async function buscarDireccion(texto, pedir) {
  for (const metodo of [porUsig, porNominatim]) {
    try {
      const resultado = await metodo(texto, pedir);
      if (resultado && Number.isFinite(resultado.lat) && Number.isFinite(resultado.lon)) return resultado;
    } catch {
      // Si un servicio falla probamos con el siguiente.
    }
  }
  return null;
}

export async function geocodificar(texto, { red, pedir = fetch } = {}) {
  if (red) {
    const lugar = buscarLugar(red, texto);
    if (lugar) return { lat: lugar.lat, lon: lugar.lon, nombre: lugar.nombre, fuente: 'lugar' };
  }
  const encontrado = await buscarDireccion(texto, pedir);
  if (encontrado) return encontrado;

  const corregido = corregirDireccion(red, texto);
  if (corregido) {
    const resultado = await buscarDireccion(corregido, pedir);
    if (resultado && !resultado.ambiguo) return { ...resultado, nombre: corregido, corregidoDe: texto };
  }
  return null;
}
