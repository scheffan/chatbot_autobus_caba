import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nombreDeParada, cuadras, indicaciones, resumen, buscarViajes, entenderPedido } from '../../motor/index.js';
import { redDePrueba } from './red-de-prueba.js';

test('nombres de paradas legibles', () => {
  assert.equal(nombreDeParada('1079 PAZ GRAL. AV.'), 'Av. Gral. Paz 1079');
  assert.equal(nombreDeParada('AVENIDA EVA PERÓN 1249-1299'), 'Av. Eva Perón 1249');
  assert.equal(nombreDeParada('4273 LAS HERAS GENERAL AV.'), 'Av. General Las Heras 4273');
  assert.equal(nombreDeParada('1053 BROWN ALTE. AV.'), 'Av. Alte. Brown 1053');
  assert.equal(nombreDeParada('300 PLAZA DE LOS VIRREYES'), 'Plaza de los Virreyes 300');
});

test('cuadras', () => {
  assert.equal(cuadras(30), 'unos pasos');
  assert.equal(cuadras(120), '1 cuadra');
  assert.equal(cuadras(420), '4 cuadras');
});

test('indicaciones con referencias', () => {
  const red = redDePrueba();
  const r = buscarViajes(red, { lat: -34.6, lon: -58.45 }, { lat: -34.57, lon: -58.4 }, { dia: 'habil', hora: 10 });
  const op = r.opciones.find((o) => o.tipo === 'trasbordo');
  const pasos = indicaciones(red, op, { destino: 'la Plaza Italia' });
  assert.match(pasos[0], /^🚏 Andá a la parada de Av\. Rivadavia 1000, frente al Obelisco\.$/);
  assert.match(pasos[1], /^🚌 Tomá el 10 \(ramal A\) hacia Liniers\. Pasa cada 10 min aprox\.$/);
  assert.ok(pasos.includes('🔁 Bajate y andá a la parada de Av. Gral. Paz 500, a unos pasos.'));
  assert.ok(pasos.some((p) => p.includes('Tomá el 20 hacia Av. Gral. Paz 800')));
  assert.ok(pasos.some((p) => p.endsWith('te bajás en Av. Gral. Paz 800, frente a la Plaza Italia.')));
  assert.equal(pasos.at(-1), '📍 Llegaste a la Plaza Italia.');
  assert.match(resumen(op), /^el 10 \(ramal A\) y después el 20, unos \d+ minutos en total$/);
});

test('entiende pedidos escritos de distintas formas', () => {
  assert.deepEqual(entenderPedido('quiero ir de Corrientes 800 a Plaza Italia'), { origen: 'Corrientes 800', destino: 'Plaza Italia' });
  assert.deepEqual(entenderPedido('Hola! cómo llego a Rivadavia 6300 desde Constitución?'), { origen: 'Constitución', destino: 'Rivadavia 6300' });
  assert.deepEqual(entenderPedido('Cabildo y Juramento -> Obelisco'), { origen: 'Cabildo y Juramento', destino: 'Obelisco' });
  assert.deepEqual(entenderPedido('de la calle Defensa 500 hasta el Obelisco'), { origen: 'Defensa 500', destino: 'el Obelisco' });
  assert.deepEqual(entenderPedido('quiero ir del Obelisco al Congreso'), { origen: 'Obelisco', destino: 'Congreso' });
  assert.equal(entenderPedido('hola'), null);
});
