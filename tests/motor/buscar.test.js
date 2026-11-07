import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buscarViajes, frecuencia, minutosCaminando, ahoraEnBuenosAires } from '../../motor/index.js';
import { redDePrueba } from './red-de-prueba.js';

const red = redDePrueba();

test('viaje directo: encuentra la línea y la parada más cercana', () => {
  const r = buscarViajes(red, { lat: -34.6005, lon: -58.45 }, { lat: -34.6, lon: -58.42 }, { dia: 'habil', hora: 10 });
  const [op] = r.opciones;
  assert.equal(op.tipo, 'directo');
  const bondi = op.tramos.find((t) => t.tipo === 'colectivo');
  assert.equal(bondi.linea, '10');
  assert.equal(bondi.desde, 0);
  assert.equal(bondi.hasta, 3);
  assert.equal(bondi.minutos, 9);
});

test('no toma un colectivo que va para el otro lado', () => {
  const r = buscarViajes(red, { lat: -34.6, lon: -58.41 }, { lat: -34.6, lon: -58.44 }, { dia: 'habil', hora: 10 });
  for (const op of r.opciones) {
    for (const t of op.tramos.filter((x) => x.tipo === 'colectivo')) assert.notEqual(t.recorrido, 0);
  }
});

test('con trasbordo: se baja del 10 y camina hasta el 20', () => {
  const r = buscarViajes(red, { lat: -34.6, lon: -58.45 }, { lat: -34.57, lon: -58.4 }, { dia: 'habil', hora: 10 });
  const op = r.opciones.find((o) => o.tipo === 'trasbordo');
  assert.ok(op, 'debería haber una opción con trasbordo');
  const lineas = op.tramos.filter((t) => t.tipo === 'colectivo').map((t) => t.linea);
  assert.deepEqual(lineas, ['10', '20']);
  const caminata = op.tramos[2];
  assert.equal(caminata.tipo, 'caminar');
  assert.ok(caminata.metros > 40 && caminata.metros < 70);
});

test('el domingo, sin servicio, no hay opciones', () => {
  const r = buscarViajes(red, { lat: -34.6, lon: -58.45 }, { lat: -34.6, lon: -58.42 }, { dia: 'domingo', hora: 10 });
  assert.equal(r.opciones.length, 0);
});

test('avisa cuando conviene caminar', () => {
  const r = buscarViajes(red, { lat: -34.6, lon: -58.45 }, { lat: -34.6, lon: -58.445 }, { dia: 'habil', hora: 10 });
  assert.ok(r.caminando);
  assert.ok(r.caminando.minutos < 10);
});

test('frecuencia y caminata', () => {
  const f = frecuencia(red.recorridos[0], 'habil', 8);
  assert.equal(f.cada, 10);
  assert.equal(f.espera, 5);
  assert.equal(frecuencia(red.recorridos[0], 'domingo', 8), null);
  assert.equal(minutosCaminando(600), 10);
});

test('día y hora en Buenos Aires', () => {
  assert.deepEqual(ahoraEnBuenosAires(new Date('2026-11-07T15:00:00Z')), { dia: 'sabado', hora: 12 });
  assert.deepEqual(ahoraEnBuenosAires(new Date('2026-11-09T02:30:00Z')), { dia: 'domingo', hora: 23 });
  assert.deepEqual(ahoraEnBuenosAires(new Date('2026-11-10T12:00:00Z')), { dia: 'habil', hora: 9 });
});
