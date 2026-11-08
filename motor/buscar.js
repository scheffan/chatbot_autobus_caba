// Buscador de viajes en colectivo.
//
// La idea es la de la Guía T: desde donde estás y desde adonde vas se
// buscan paradas en anillos que se van agrandando (300 m, 600 m, …).
// Con esas paradas se arman viajes directos y, si hace falta, con un
// trasbordo caminando hasta otra parada cercana.
import { distancia } from './geo.js';

export const VELOCIDAD_CAMINANDO = 75; // metros por minuto (4,5 km/h)
const FACTOR_CALLES = 1.25; // las calles no van en línea recta
const ANILLOS = [300, 600, 900, 1200];
const PENALIDAD_TRASBORDO = 5; // minutos: bajarse y subirse a otro cansa
const ESPERA_MAXIMA = 20;

export function minutosCaminando(metros) {
  return (metros * FACTOR_CALLES) / VELOCIDAD_CAMINANDO;
}

// Cuánto se espera en promedio y cada cuánto pasa, según la hora.
export function frecuencia(recorrido, dia, hora) {
  const porHora = recorrido.frecuencia?.[dia];
  if (!porHora) return null;
  const n = porHora[hora % 24] + porHora[(hora + 1) % 24] * 0.5;
  if (n < 1) return null; // menos de un colectivo por hora: no lo ofrecemos
  const cada = 60 / (n / 1.5);
  return { cada: Math.max(1, Math.round(cada)), espera: Math.min(cada / 2, ESPERA_MAXIMA) };
}

function clave(recorrido) {
  return `${recorrido.linea}|${recorrido.ramal}|${recorrido.hacia}`;
}

function tramoColectivo(red, ri, desde, hasta, frec) {
  const r = red.recorridos[ri];
  return {
    tipo: 'colectivo',
    recorrido: ri,
    linea: r.linea,
    ramal: r.ramal,
    variosRamales: r.variosRamales,
    hacia: r.hacia || red.paradas[r.paradas[r.paradas.length - 1]].nombre,
    haciaEsParada: !r.hacia,
    desde: r.paradas[desde],
    hasta: r.paradas[hasta],
    paradas: hasta - desde,
    minutos: r.minutos[hasta] - r.minutos[desde],
    espera: frec.espera,
    cada: frec.cada,
    camino: r.paradas.slice(desde, hasta + 1),
  };
}

function tramoCaminar(metros, hasta) {
  return { tipo: 'caminar', metros: Math.round(metros), minutos: minutosCaminando(metros), hasta };
}

function buscarDirectos(red, origenes, destinos, dia, hora) {
  const metrosDestino = new Map(destinos.map((d) => [d.i, d.dist]));
  const mejores = new Map();
  for (const o of origenes) {
    for (const [ri, pos] of red.pasan[o.i]) {
      const r = red.recorridos[ri];
      const frec = frecuencia(r, dia, hora);
      if (!frec) continue;
      for (let j = pos + 1; j < r.paradas.length; j++) {
        const dd = metrosDestino.get(r.paradas[j]);
        if (dd === undefined) continue;
        const total = minutosCaminando(o.dist) + frec.espera + (r.minutos[j] - r.minutos[pos]) + minutosCaminando(dd);
        const k = clave(r);
        const actual = mejores.get(k);
        if (!actual || total < actual.total) {
          mejores.set(k, { total, ri, pos, j, o, dd, frec });
        }
      }
    }
  }
  return [...mejores.values()].map((m) => ({
    tipo: 'directo',
    total: m.total,
    tramos: [
      tramoCaminar(m.o.dist, red.recorridos[m.ri].paradas[m.pos]),
      tramoColectivo(red, m.ri, m.pos, m.j, m.frec),
      tramoCaminar(m.dd, null),
    ],
  }));
}

// Guarda las dos mejores opciones por parada, de líneas distintas.
function guardar(mapa, parada, entrada) {
  const lista = mapa.get(parada);
  if (!lista) {
    mapa.set(parada, [entrada]);
    return;
  }
  const linea = entrada.linea;
  const igual = lista.findIndex((e) => e.linea === linea);
  if (igual >= 0) {
    if (entrada.costo < lista[igual].costo) lista[igual] = entrada;
  } else {
    lista.push(entrada);
  }
  lista.sort((a, b) => a.costo - b.costo);
  if (lista.length > 2) lista.length = 2;
}

function buscarConTrasbordo(red, origenes, destinos, dia, hora) {
  // Hacia adelante: a qué paradas llego con un colectivo desde el origen.
  const llego = new Map();
  for (const o of origenes) {
    for (const [ri, pos] of red.pasan[o.i]) {
      const r = red.recorridos[ri];
      const frec = frecuencia(r, dia, hora);
      if (!frec) continue;
      const base = minutosCaminando(o.dist) + frec.espera;
      for (let j = pos + 1; j < r.paradas.length; j++) {
        guardar(llego, r.paradas[j], { costo: base + r.minutos[j] - r.minutos[pos], linea: r.linea, ri, pos, j, o, frec });
      }
    }
  }
  // Hacia atrás: desde qué paradas llego al destino con un colectivo.
  const salgo = new Map();
  for (const d of destinos) {
    for (const [ri, j] of red.pasan[d.i]) {
      const r = red.recorridos[ri];
      const frec = frecuencia(r, dia, hora);
      if (!frec) continue;
      const base = minutosCaminando(d.dist) + frec.espera;
      for (let k = 0; k < j; k++) {
        guardar(salgo, r.paradas[k], { costo: base + r.minutos[j] - r.minutos[k], linea: r.linea, ri, k, j, d, frec });
      }
    }
  }
  // Unimos: me bajo en A, camino hasta B (cerca) y tomo el segundo.
  const mejores = new Map();
  for (const [a, primeros] of llego) {
    const vecinas = red.vecinas(a);
    for (let v = 0; v < vecinas.length; v += 2) {
      const b = vecinas[v];
      const dist = vecinas[v + 1];
      const segundos = salgo.get(b);
      if (!segundos) continue;
      for (const uno of primeros) {
        for (const dos of segundos) {
          if (uno.linea === dos.linea) continue;
          const total = uno.costo + minutosCaminando(dist) + dos.costo + PENALIDAD_TRASBORDO;
          const k = `${clave(red.recorridos[uno.ri])}>${clave(red.recorridos[dos.ri])}`;
          const actual = mejores.get(k);
          if (!actual || total < actual.total) mejores.set(k, { total, uno, dos, a, b, dist });
        }
      }
    }
  }
  return [...mejores.values()].map((m) => ({
    tipo: 'trasbordo',
    total: m.total - PENALIDAD_TRASBORDO,
    orden: m.total,
    tramos: [
      tramoCaminar(m.uno.o.dist, red.recorridos[m.uno.ri].paradas[m.uno.pos]),
      tramoColectivo(red, m.uno.ri, m.uno.pos, m.uno.j, m.uno.frec),
      tramoCaminar(m.dist, m.b),
      tramoColectivo(red, m.dos.ri, m.dos.k, m.dos.j, m.dos.frec),
      tramoCaminar(m.dos.d.dist, null),
    ],
  }));
}

// Elige opciones variadas: no tres veces la misma línea.
function elegir(opciones, cantidad) {
  const elegidas = [];
  const usadas = new Set();
  for (const op of opciones.sort((a, b) => (a.orden ?? a.total) - (b.orden ?? b.total))) {
    const lineas = op.tramos.filter((t) => t.tipo === 'colectivo').map((t) => t.linea).join('+');
    if (usadas.has(lineas)) continue;
    usadas.add(lineas);
    elegidas.push(op);
    if (elegidas.length >= cantidad) break;
  }
  return elegidas;
}

export function buscarViajes(red, origen, destino, { dia = 'habil', hora = 12, cantidad = 3 } = {}) {
  const directo = distancia(origen.lat, origen.lon, destino.lat, destino.lon);
  const resultado = { caminando: null, opciones: [], anillo: null };
  if (directo < 900) {
    resultado.caminando = { metros: Math.round(directo), minutos: minutosCaminando(directo) };
  }

  let directos = [];
  let trasbordos = [];
  for (const radio of ANILLOS) {
    const origenes = red.grilla.cercanos(origen.lat, origen.lon, radio);
    const destinos = red.grilla.cercanos(destino.lat, destino.lon, radio);
    if (!origenes.length || !destinos.length) continue;
    directos = buscarDirectos(red, origenes, destinos, dia, hora);
    resultado.anillo = radio;
    if (directos.length >= cantidad) break;
    if (radio >= 600) {
      trasbordos = buscarConTrasbordo(red, origenes.slice(0, 60), destinos.slice(0, 60), dia, hora);
      if (directos.length + trasbordos.length >= cantidad) break;
    }
  }

  // Un trasbordo solo vale la pena si ahorra tiempo de verdad.
  const mejorDirecto = Math.min(...directos.map((d) => d.total), Infinity);
  const utiles = trasbordos.filter((t) => directos.length < cantidad || t.orden < mejorDirecto - 10);
  resultado.opciones = elegir([...directos, ...utiles], cantidad);
  return resultado;
}

// Tipo de día y hora en Buenos Aires.
export function ahoraEnBuenosAires(fecha = new Date()) {
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Argentina/Buenos_Aires',
      weekday: 'short',
      hour: 'numeric',
      hourCycle: 'h23',
    })
      .formatToParts(fecha)
      .map((p) => [p.type, p.value]),
  );
  const dia = partes.weekday === 'Sat' ? 'sabado' : partes.weekday === 'Sun' ? 'domingo' : 'habil';
  return { dia, hora: Number(partes.hour) };
}
