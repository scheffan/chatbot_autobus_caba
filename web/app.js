import {
  prepararRed, buscarViajes, ahoraEnBuenosAires, indicaciones, resumen,
  geocodificar, nombreLinea, distancia,
} from './motor/index.js';

const $ = (id) => document.getElementById(id);
const estado = $('estado');
const COLORES = ['var(--linea-1)', 'var(--linea-2)'];
const COLORES_MAPA = ['#0b7fab', '#d9480f'];

const mapa = L.map('mapa', { zoomControl: true }).setView([-34.6037, -58.4416], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; colaboradores de OpenStreetMap',
}).addTo(mapa);
const capa = L.layerGroup().addTo(mapa);

let red = null;
const puntos = { origen: null, destino: null };
let ultimas = [];

async function cargar() {
  try {
    const [datos, lugares] = await Promise.all([
      fetch('datos/red.json').then((r) => r.json()),
      fetch('datos/referencias.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    red = prepararRed(datos, lugares);
    estado.textContent = `Listo: ${red.recorridos.length.toLocaleString('es-AR')} recorridos y ${red.paradas.length.toLocaleString('es-AR')} paradas.`;
    desdeEnlace();
  } catch (e) {
    estado.textContent = 'No pude cargar los datos. Probá recargar la página.';
  }
}

function marcador(tipo, lat, lon) {
  const emoji = tipo === 'origen' ? '🟢' : '🏁';
  return L.marker([lat, lon], {
    icon: L.divIcon({ className: '', html: `<span style="font-size:26px">${emoji}</span>`, iconAnchor: [13, 26] }),
  });
}

async function resolver(tipo) {
  const valor = $(tipo).value.trim();
  if (puntos[tipo] && puntos[tipo].texto === valor) return puntos[tipo];
  const lugar = await geocodificar(valor, { red });
  if (!lugar) throw new Error(`No encontré "${valor}". Probá con calle y altura, una esquina ("Corrientes y Callao") o tocá el mapa.`);
  puntos[tipo] = { ...lugar, texto: valor };
  return puntos[tipo];
}

function dibujar(opcion, origen, destino) {
  capa.clearLayers();
  marcador('origen', origen.lat, origen.lon).addTo(capa);
  marcador('destino', destino.lat, destino.lon).addTo(capa);
  const limites = [[origen.lat, origen.lon], [destino.lat, destino.lon]];
  let anterior = [origen.lat, origen.lon];
  let colectivo = 0;
  for (const t of opcion.tramos) {
    if (t.tipo === 'caminar') {
      const fin = t.hasta === null ? [destino.lat, destino.lon] : [red.paradas[t.hasta].lat, red.paradas[t.hasta].lon];
      L.polyline([anterior, fin], { color: '#6b7c85', dashArray: '4 8', weight: 4 }).addTo(capa);
      anterior = fin;
    } else {
      const coords = t.camino.map((p) => [red.paradas[p].lat, red.paradas[p].lon]);
      L.polyline(coords, { color: COLORES_MAPA[colectivo % 2], weight: 6, opacity: 0.85 }).addTo(capa)
        .bindTooltip(`Línea ${nombreLinea(t)}`);
      L.circleMarker(coords[0], { radius: 6, color: COLORES_MAPA[colectivo % 2], fillOpacity: 1 }).addTo(capa)
        .bindPopup(`Subís al ${nombreLinea(t)}`);
      L.circleMarker(coords[coords.length - 1], { radius: 6, color: COLORES_MAPA[colectivo % 2], fillOpacity: 1 }).addTo(capa)
        .bindPopup('Te bajás acá');
      limites.push(...coords);
      anterior = coords[coords.length - 1];
      colectivo++;
    }
  }
  mapa.fitBounds(limites, { padding: [30, 30] });
}

function mostrar(resultado, origen, destino) {
  const caja = $('resultados');
  caja.innerHTML = '';
  ultimas = resultado.opciones;
  if (resultado.caminando && resultado.caminando.minutos < 12) {
    const aviso = document.createElement('p');
    aviso.className = 'estado';
    aviso.textContent = `🚶 Está cerca: caminando son unos ${Math.round(resultado.caminando.minutos)} minutos.`;
    caja.append(aviso);
  }
  if (!resultado.opciones.length) {
    estado.textContent = 'No encontré colectivos para ese viaje a esta hora. Probá con puntos más cercanos a una avenida.';
    capa.clearLayers();
    return;
  }
  estado.textContent = `Encontré ${resultado.opciones.length} opciones (paradas buscadas hasta ${resultado.anillo} m).`;
  resultado.opciones.forEach((op, n) => {
    const tarjeta = document.createElement('article');
    tarjeta.className = 'opcion';
    const chapas = op.tramos.filter((t) => t.tipo === 'colectivo')
      .map((t, i) => `<span class="chapa" style="background:${COLORES[i % 2]}">${t.linea}</span>`).join(' ');
    tarjeta.innerHTML = `<h3><span>${chapas}</span><small>~${Math.round(op.total)} min</small></h3>`;
    const lista = document.createElement('ol');
    for (const paso of indicaciones(red, op, { destino: destino.nombre || 'tu destino' })) {
      const li = document.createElement('li');
      li.textContent = paso;
      lista.append(li);
    }
    tarjeta.append(lista);
    tarjeta.title = resumen(op);
    tarjeta.addEventListener('click', () => elegir(n, origen, destino));
    caja.append(tarjeta);
  });
  elegir(0, origen, destino);
}

function elegir(n, origen, destino) {
  document.querySelectorAll('.opcion').forEach((el, i) => el.classList.toggle('activa', i === n));
  dibujar(ultimas[n], origen, destino);
}

$('formulario').addEventListener('submit', async (evento) => {
  evento.preventDefault();
  if (!red) return;
  const boton = $('buscar');
  boton.disabled = true;
  estado.textContent = 'Buscando…';
  try {
    const [origen, destino] = await Promise.all([resolver('origen'), resolver('destino')]);
    if (distancia(origen.lat, origen.lon, destino.lat, destino.lon) > 60000) {
      throw new Error('Esos dos puntos están muy lejos entre sí. ¿Seguro que son del AMBA?');
    }
    const { dia, hora } = ahoraEnBuenosAires();
    mostrar(buscarViajes(red, origen, destino, { dia, hora }), origen, destino);
  } catch (e) {
    estado.textContent = e.message;
  } finally {
    boton.disabled = false;
  }
});

// Tocar el mapa: primero el origen, después el destino.
mapa.on('click', (e) => {
  const tipo = !puntos.origen || puntos.destino ? 'origen' : 'destino';
  if (tipo === 'origen') puntos.destino = null;
  const texto = `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
  puntos[tipo] = { lat: e.latlng.lat, lon: e.latlng.lng, nombre: tipo === 'destino' ? 'el punto que marcaste' : texto, texto };
  $(tipo).value = texto;
  if (tipo === 'origen') {
    capa.clearLayers();
    marcador('origen', e.latlng.lat, e.latlng.lng).addTo(capa);
    $('destino').value = '';
    estado.textContent = 'Ahora tocá adónde vas.';
  } else {
    $('formulario').requestSubmit();
  }
});

$('ubicacion').addEventListener('click', () => {
  if (!navigator.geolocation) return;
  estado.textContent = 'Buscando tu ubicación…';
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const texto = 'Mi ubicación';
      puntos.origen = { lat: pos.coords.latitude, lon: pos.coords.longitude, nombre: texto, texto };
      $('origen').value = texto;
      estado.textContent = 'Listo, ahora escribí adónde vas.';
    },
    () => { estado.textContent = 'No pude obtener tu ubicación.'; },
  );
});

// Enlaces del bot: ?de=lat,lon&a=lat,lon (opcional &dn= y &an= con los nombres).
function leerPunto(valor) {
  const m = (valor || '').match(/^(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)$/);
  return m ? { lat: Number(m[1]), lon: Number(m[2]) } : null;
}

function desdeEnlace() {
  const q = new URLSearchParams(location.search);
  const de = leerPunto(q.get('de'));
  const a = leerPunto(q.get('a'));
  if (!de || !a) return;
  const nombres = { origen: q.get('dn') || q.get('de'), destino: q.get('an') || q.get('a') };
  for (const [tipo, p] of [['origen', de], ['destino', a]]) {
    puntos[tipo] = { ...p, nombre: nombres[tipo], texto: nombres[tipo] };
    $(tipo).value = nombres[tipo];
  }
  $('formulario').requestSubmit();
}

cargar();
