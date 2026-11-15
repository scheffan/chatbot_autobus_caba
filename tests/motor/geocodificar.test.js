import { test } from 'node:test';
import assert from 'node:assert/strict';
import { geocodificar, corregirDireccion, distanciaEdicion } from '../../motor/geocodificar.js';
import { responder } from '../../worker/bot.js';
import { redDePrueba } from './red-de-prueba.js';

const red = redDePrueba();
const json = (cuerpo) => ({ ok: true, json: async () => cuerpo });
const usigVacio = { direccionesNormalizadas: [], errorMessage: 'Calle inexistente' };

// Imita a USIG y Nominatim: solo conocen "Rivadavia 1200" y una calle "Mar del Plata".
const servicios = async (url) => {
  const u = decodeURIComponent(url);
  if (u.includes('usig')) {
    if (u.includes('direccion=Rivadavia 1200')) return json({ direccionesNormalizadas: [{ coordenadas: { x: '-58.43', y: '-34.6' } }] });
    return json(usigVacio);
  }
  if (u.includes('Mar del Plata')) {
    return json([{ class: 'highway', type: 'residential', lat: '-34.6245', lon: '-58.4875', address: { suburb: 'Floresta' } }]);
  }
  return json([]);
};

test('distancia de edición', () => {
  assert.equal(distanciaEdicion('corientes', 'corrientes'), 1);
  assert.equal(distanciaEdicion('rivadabia', 'rivadavia'), 1);
  assert.equal(distanciaEdicion('abc', 'abc'), 0);
});

test('corrige el nombre de la calle con las calles de la red', () => {
  assert.equal(corregirDireccion(red, 'Rivadabia 1200'), 'Rivadavia 1200');
  assert.equal(corregirDireccion(red, 'Rivadavia 1200'), null); // bien escrita: no toca nada
  assert.equal(corregirDireccion(red, 'Xyzwq 1200'), null); // demasiado distinta: no adivina
  assert.equal(corregirDireccion(red, 'Rivadabia y Paz'), 'Rivadavia y Paz');
});

test('una dirección con error de tipeo se encuentra y se avisa la corrección', async () => {
  const punto = await geocodificar('Rivadabia 1200', { red, pedir: servicios });
  assert.equal(punto.nombre, 'Rivadavia 1200');
  assert.equal(punto.corregidoDe, 'Rivadabia 1200');
});

test('una calle sin altura queda marcada como ambigua', async () => {
  const punto = await geocodificar('Mar del Plata', { red, pedir: servicios });
  assert.equal(punto.ambiguo, 'calle');
  assert.equal(punto.zona, 'Floresta');
});

const update = (text) => ({ update_id: 1, message: { message_id: 5, chat: { id: 42 }, text } });
const opciones = { red, pedir: servicios, urlWeb: 'https://x/', ahora: () => ({ dia: 'habil', hora: 10 }) };

test('el bot no arma un viaje a una calle ambigua (bug "de Obelisco a Mar del Plata")', async () => {
  const r = await responder(update('de Obelisco a Mar del Plata'), opciones);
  assert.doesNotMatch(r.text, /Opción 1/);
  assert.match(r.text, /calle llamada "Mar del Plata" en Floresta/);
  assert.match(r.text, /fuera de mi zona/);
});

test('el bot cuenta qué corrigió', async () => {
  const r = await responder(update('de Rivadabia 1200 a Plaza Italia'), opciones);
  assert.match(r.text, /Opción 1/);
  assert.match(r.text, /Entendí <i>Rivadavia 1200<\/i> \(escribiste <i>Rivadabia 1200<\/i>\)/);
});
