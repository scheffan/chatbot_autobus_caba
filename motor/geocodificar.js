// Convierte "Corrientes 800", "Corrientes y Callao" u "Obelisco" en coordenadas.
//
// 1) Lugares conocidos de OpenStreetMap que ya tenemos cargados.
// 2) El normalizador de direcciones de la Ciudad (USIG), que entiende
//    alturas e intersecciones de CABA.
// 3) Nominatim (OpenStreetMap) para el resto del AMBA.
import { buscarLugar } from './red.js';

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

async function porNominatim(texto, pedir) {
  const consulta = /buenos aires|caba|argentina/i.test(texto) ? texto : `${texto}, Buenos Aires`;
  const url = `${NOMINATIM}?format=json&limit=1&countrycodes=ar&bounded=1&viewbox=${CAJA_AMBA}&q=${encodeURIComponent(consulta)}`;
  const respuesta = await pedir(url, { headers: { 'Accept-Language': 'es' } });
  if (!respuesta.ok) return null;
  const [d] = await respuesta.json();
  if (!d) return null;
  return { lat: Number(d.lat), lon: Number(d.lon), nombre: texto, fuente: 'nominatim' };
}

export async function geocodificar(texto, { red, pedir = fetch } = {}) {
  if (red) {
    const lugar = buscarLugar(red, texto);
    if (lugar) return { lat: lugar.lat, lon: lugar.lon, nombre: lugar.nombre, fuente: 'lugar' };
  }
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
