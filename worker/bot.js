// Lógica del bot de Telegram: recibe un "update" y devuelve el mensaje a mandar.
// No conoce el token: la respuesta viaja en el cuerpo del webhook.
import {
  buscarViajes, ahoraEnBuenosAires, indicaciones, nombreLinea, geocodificar, entenderPedido, distancia, contraer,
} from '../motor/index.js';

const MAX_DISTANCIA = 60000;
const MARCA_SALIDA = /Salida: (-?\d+\.\d+), (-?\d+\.\d+)/;

export const AYUDA = [
  '🚌 <b>¡Hola! Soy Bondi CABA.</b>',
  '',
  'Decime de dónde salís y adónde vas, y te digo qué colectivo tomar, dónde está la parada y cada cuánto pasa.',
  '',
  'Podés escribir, por ejemplo:',
  '• <i>de Corrientes 800 a Plaza Italia</i>',
  '• <i>quiero ir de Cabildo y Juramento al Obelisco</i>',
  '• <i>cómo llego a Rivadavia 6300 desde Constitución</i>',
  '',
  '📍 También podés mandarme tu ubicación y después me decís adónde vas.',
].join('\n');

export function escapar(texto) {
  return String(texto).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function mensaje(chatId, texto, extra = {}) {
  return {
    method: 'sendMessage',
    chat_id: chatId,
    text: texto,
    parse_mode: 'HTML',
    disable_web_page_preview: true,
    ...extra,
  };
}

function coordenadas(p) {
  return `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`;
}

export function enlaceMapa(urlWeb, origen, destino) {
  const q = new URLSearchParams({ de: coordenadas(origen), a: coordenadas(destino) });
  if (origen.nombre) q.set('dn', origen.nombre);
  if (destino.nombre) q.set('an', destino.nombre);
  return `${urlWeb}?${q}`;
}

export function armarRespuesta(red, resultado, origen, destino) {
  const titulo = contraer(`De ${escapar(origen.nombre)} a ${escapar(destino.nombre)}`).replace(/^De el /, 'Del ');
  const lineas = [`🚌 <b>${titulo}</b>`];
  if (resultado.caminando && resultado.caminando.minutos < 12) {
    lineas.push('', `🚶 Está cerca: caminando son unos ${Math.round(resultado.caminando.minutos)} minutos.`);
  }
  if (!resultado.opciones.length) {
    lineas.push('', 'No encontré colectivos para ese viaje a esta hora. Probá con un punto más cerca de una avenida.');
    return lineas.join('\n');
  }
  resultado.opciones.forEach((op, n) => {
    const chapas = op.tramos.filter((t) => t.tipo === 'colectivo').map(nombreLinea).join(' + ');
    lineas.push('', `<b>Opción ${n + 1}: ${escapar(chapas)}</b> · unos ${Math.round(op.total)} min`);
    for (const paso of indicaciones(red, op, { destino: destino.nombre })) lineas.push(escapar(paso));
  });
  lineas.push('', '<i>Los tiempos son estimados.</i>');
  return lineas.join('\n');
}

export async function responder(update, { red, pedir = fetch, urlWeb, ahora = ahoraEnBuenosAires }) {
  const m = update.message;
  if (!m || !m.chat) return null;
  const chatId = m.chat.id;

  if (m.location) {
    return mensaje(
      chatId,
      `📍 Listo, salís de ahí. ¿Adónde vas? Respondé este mensaje con la dirección o el lugar.\n\nSalida: ${m.location.latitude.toFixed(5)}, ${m.location.longitude.toFixed(5)}`,
      { reply_markup: { force_reply: true, input_field_placeholder: 'Ej: Plaza Italia' } },
    );
  }

  const texto = (m.text || '').trim();
  if (!texto) return null;
  if (/^\/(start|ayuda|help)\b/i.test(texto)) return mensaje(chatId, AYUDA);

  // Si responde al pedido de destino, la salida viene en el mensaje del bot.
  let pedido = null;
  let origenFijo = null;
  const respondido = m.reply_to_message?.text?.match(MARCA_SALIDA);
  if (respondido) {
    origenFijo = { lat: Number(respondido[1]), lon: Number(respondido[2]), nombre: 'tu ubicación' };
    pedido = { origen: null, destino: texto };
  } else {
    pedido = entenderPedido(texto);
  }
  if (!pedido) {
    return mensaje(chatId, 'No te entendí 🤔 Escribime algo como <i>de Corrientes 800 a Plaza Italia</i>, o mandame tu ubicación 📍.');
  }

  const [origen, destino] = await Promise.all([
    origenFijo ?? geocodificar(pedido.origen, { red, pedir }),
    geocodificar(pedido.destino, { red, pedir }),
  ]);
  const faltan = [[origen, pedido.origen], [destino, pedido.destino]].filter(([p]) => !p).map(([, t]) => `"${escapar(t)}"`);
  if (faltan.length) {
    return mensaje(chatId, `No encontré ${faltan.join(' ni ')}. Probá con calle y altura (<i>Corrientes 800</i>), una esquina (<i>Corrientes y Callao</i>) o un lugar conocido.`);
  }
  if (distancia(origen.lat, origen.lon, destino.lat, destino.lon) > MAX_DISTANCIA) {
    return mensaje(chatId, 'Esos dos puntos están muy lejos entre sí. ¿Seguro que son del AMBA?');
  }

  const { dia, hora } = ahora();
  const resultado = buscarViajes(red, origen, destino, { dia, hora });
  const extra = urlWeb && resultado.opciones.length
    ? { reply_markup: { inline_keyboard: [[{ text: '🗺️ Ver en el mapa', url: enlaceMapa(urlWeb, origen, destino) }]] } }
    : {};
  return mensaje(chatId, armarRespuesta(red, resultado, origen, destino), extra);
}
