// Cuentas geográficas y una grilla para encontrar rápido lo que está cerca.

const METROS_POR_GRADO = 111320;

export function distancia(lat1, lon1, lat2, lon2) {
  // Aproximación plana: sobra para distancias de una ciudad.
  const x = (lon2 - lon1) * Math.cos(((lat1 + lat2) / 2) * (Math.PI / 180));
  const y = lat2 - lat1;
  return Math.sqrt(x * x + y * y) * METROS_POR_GRADO;
}

export class Grilla {
  constructor(puntos, tamano = 0.0025) {
    this.tamano = tamano;
    this.puntos = puntos;
    this.celdas = new Map();
    puntos.forEach((p, i) => {
      const clave = this.clave(p.lat, p.lon);
      if (!this.celdas.has(clave)) this.celdas.set(clave, []);
      this.celdas.get(clave).push(i);
    });
  }

  clave(lat, lon) {
    return Math.floor(lat / this.tamano) * 100000 + Math.floor(lon / this.tamano);
  }

  // Devuelve [{i, dist}] ordenado por distancia, dentro del radio en metros.
  cercanos(lat, lon, radio) {
    const pasos = Math.ceil(radio / (this.tamano * 90000)) + 1;
    const fila = Math.floor(lat / this.tamano);
    const columna = Math.floor(lon / this.tamano);
    const salida = [];
    for (let df = -pasos; df <= pasos; df++) {
      for (let dc = -pasos; dc <= pasos; dc++) {
        const celda = this.celdas.get((fila + df) * 100000 + columna + dc);
        if (!celda) continue;
        for (const i of celda) {
          const p = this.puntos[i];
          const dist = distancia(lat, lon, p.lat, p.lon);
          if (dist <= radio) salida.push({ i, dist });
        }
      }
    }
    return salida.sort((a, b) => a.dist - b.dist);
  }
}
