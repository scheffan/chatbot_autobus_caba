// Worker de Cloudflare que atiende el webhook de @bondicaba_bot.
// Los datos se generan con datos/construir_red.py y datos/construir_referencias.py
// y el workflow "Publicar" los copia a worker/datos/ antes de subirlo.
import datos from './datos/red.json';
import lugares from './datos/referencias.json';
import { prepararRed } from '../motor/index.js';
import { responder } from './bot.js';

const red = prepararRed(datos, lugares);

// Nominatim pide identificarse con un User-Agent propio.
const pedir = (url, opciones = {}) => fetch(url, {
  ...opciones,
  headers: { 'User-Agent': 'bondicaba-bot (github.com/scheffan/chatbot_autobus_caba)', ...(opciones.headers || {}) },
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/telegram') {
      return new Response('Bondi CABA: bot de Telegram @bondicaba_bot', { headers: { 'content-type': 'text/plain; charset=utf-8' } });
    }
    if (request.method !== 'POST') return new Response('Método no permitido', { status: 405 });
    if (!env.TELEGRAM_SECRETO || request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.TELEGRAM_SECRETO) {
      return new Response('No autorizado', { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response('ok');
    }
    let respuesta = null;
    try {
      respuesta = await responder(update, { red, pedir, urlWeb: env.URL_WEB });
    } catch (error) {
      console.error(error);
      const chatId = update?.message?.chat?.id;
      if (chatId) {
        respuesta = { method: 'sendMessage', chat_id: chatId, text: 'Uy, algo falló de mi lado 😅 Probá de nuevo en un rato.' };
      }
    }
    return respuesta ? Response.json(respuesta) : new Response('ok');
  },
};
