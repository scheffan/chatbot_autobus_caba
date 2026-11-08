import { test } from 'node:test';
import assert from 'node:assert/strict';
import { responder, escapar, enlaceMapa } from '../../worker/bot.js';
import { redDePrueba } from './red-de-prueba.js';

const red = redDePrueba();
const urlWeb = 'https://ejemplo.github.io/bondi/';
const ahora = () => ({ dia: 'habil', hora: 10 });
// Sin internet: si el bot intenta geocodificar afuera, responde "no encontrado".
const sinRed = async () => ({ ok: false, json: async () => ({}) });
const opciones = { red, pedir: sinRed, urlWeb, ahora };

const update = (message) => ({ update_id: 1, message: { message_id: 5, chat: { id: 42 }, ...message } });

test('/start muestra la ayuda', async () => {
  const r = await responder(update({ text: '/start' }), opciones);
  assert.equal(r.method, 'sendMessage');
  assert.equal(r.chat_id, 42);
  assert.match(r.text, /Bondi CABA/);
});

test('un pedido con lugares conocidos devuelve el viaje y el enlace al mapa', async () => {
  const r = await responder(update({ text: 'quiero ir de Obelisco a Plaza Italia' }), opciones);
  assert.match(r.text, /<b>Del Obelisco a la Plaza Italia<\/b>/);
  assert.match(r.text, /Opción 1: 10 \(ramal A\) \+ 20/);
  assert.match(r.text, /frente al Obelisco/);
  const [[boton]] = r.reply_markup.inline_keyboard;
  assert.ok(boton.url.startsWith(`${urlWeb}?de=-34.60000%2C-58.45000&a=-34.57000%2C-58.40000`));
});

test('la ubicación pide el destino y después la usa como salida', async () => {
  const pedido = await responder(update({ location: { latitude: -34.6, longitude: -58.45 } }), opciones);
  assert.equal(pedido.reply_markup.force_reply, true);
  assert.match(pedido.text, /Salida: -34\.60000, -58\.45000/);

  const r = await responder(update({ text: 'Plaza Italia', reply_to_message: { text: pedido.text } }), opciones);
  assert.match(r.text, /De tu ubicación a la Plaza Italia/);
  assert.match(r.text, /Opción 1/);
});

test('avisa qué lugar no encontró', async () => {
  const r = await responder(update({ text: 'de Obelisco a Calle Inventada 123' }), opciones);
  assert.match(r.text, /No encontré "Inventada 123"/);
});

test('si no entiende, explica cómo pedir', async () => {
  const r = await responder(update({ text: 'hola' }), opciones);
  assert.match(r.text, /No te entendí/);
});

test('ignora lo que no es un mensaje', async () => {
  assert.equal(await responder({ update_id: 2, edited_message: {} }, opciones), null);
});

test('usa el normalizador de la Ciudad para direcciones', async () => {
  const pedidos = [];
  const pedir = async (url) => {
    pedidos.push(url);
    return { ok: true, json: async () => ({ direccionesNormalizadas: [{ direccion: 'CORRIENTES AV. 800', coordenadas: { x: '-58.45', y: '-34.6' } }] }) };
  };
  const r = await responder(update({ text: 'de Corrientes 800 a Plaza Italia' }), { ...opciones, pedir });
  assert.ok(pedidos[0].startsWith('https://servicios.usig.buenosaires.gob.ar/normalizar/?direccion=Corrientes%20800'));
  assert.match(r.text, /De Corrientes 800 a la Plaza Italia/);
});

test('escapa el HTML de lo que escribe la gente', () => {
  assert.equal(escapar('<b>&'), '&lt;b&gt;&amp;');
  assert.match(enlaceMapa(urlWeb, { lat: 1, lon: 2, nombre: 'A' }, { lat: 3, lon: 4 }), /dn=A/);
});
