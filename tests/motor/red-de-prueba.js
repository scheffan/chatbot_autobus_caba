// Una red chiquita inventada para las pruebas.
//
//                      20 ─ S9 (-34.570)
//                       │
//                      S8 (-34.580)
//                       │
//                      S7 (-34.590)
//                       │
//  S0 ─ S1 ─ S2 ─ S3 ─ S4 ─ S5 (línea 10, de oeste a este)   S6 a 55 m de S5
import { prepararRed } from '../../motor/index.js';

const todoElDia = (n) => ({ habil: Array(24).fill(n), sabado: Array(24).fill(n), domingo: Array(24).fill(0) });

export function datosDePrueba() {
  const paradas = [];
  for (let k = 0; k < 6; k++) paradas.push([-34.6, -58.45 + k * 0.01, `${1000 + k * 100} RIVADAVIA AV.`]);
  paradas.push([-34.6005, -58.4, '500 PAZ GRAL. AV.']);
  paradas.push([-34.59, -58.4, '600 PAZ GRAL. AV.']);
  paradas.push([-34.58, -58.4, '700 PAZ GRAL. AV.']);
  paradas.push([-34.57, -58.4, '800 PAZ GRAL. AV.']);
  return {
    version: 1,
    fuente: 'prueba',
    paradas,
    recorridos: [
      { linea: '10', ramal: 'A', descripcion: '', hacia: 'Liniers', paradas: [0, 1, 2, 3, 4, 5], minutos: [0, 3, 6, 9, 12, 15], frecuencia: todoElDia(6) },
      { linea: '10', ramal: 'B', descripcion: '', hacia: '', paradas: [5, 4, 3], minutos: [0, 3, 6], frecuencia: todoElDia(2) },
      { linea: '20', ramal: '', descripcion: '', hacia: '', paradas: [6, 7, 8, 9], minutos: [0, 4, 8, 12], frecuencia: todoElDia(4) },
    ],
  };
}

export const LUGARES = [
  [-34.6, -58.45, 'el Obelisco', 'monumento'],
  [-34.57, -58.4, 'la Plaza Italia', 'plaza'],
  [-34.5903, -58.4, 'el Banco Nación', 'banco'],
];

export function redDePrueba() {
  return prepararRed(datosDePrueba(), LUGARES);
}
