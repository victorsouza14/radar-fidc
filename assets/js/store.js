import { cacheData } from "./components/fetch-error.js";

const DATA_URL = "data.json";

let _data = null;

function isValid(payload) {
  return payload
    && typeof payload === "object"
    && payload.macro
    && payload.fidcs?.detalhe
    && payload.fidcs?.stats?.distribuicao
    && payload.clientes?.lista
    && payload.matches?.lista
    && payload.credit?.empresas;
}

export async function load() {
  const url = `${DATA_URL}?v=${Date.now()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} ao carregar ${DATA_URL}`);
  const json = await res.json();
  if (!isValid(json)) throw new Error(`Payload de ${DATA_URL} com shape inválido.`);
  // Cache do payload bem-sucedido — usado pelo fetch-error em caso de
  // falha futura para exibir "última cópia conhecida".
  cacheData(json);
  _data = Object.freeze(json);
  return _data;
}

function ensure() {
  if (!_data) throw new Error("Store ainda não foi inicializado. Chame load() antes.");
  return _data;
}

export const Store = {
  macro:  () => ensure().macro,
  config: () => ensure().config ?? {},

  fidcs: {
    stats:   () => ensure().fidcs.stats,
    detalhe: () => ensure().fidcs.detalhe,
  },

  clientes: {
    total:        () => ensure().clientes.total,
    distribuicao: () => ensure().clientes.distribuicao_perfil ?? {},
    lista:        () => ensure().clientes.lista,
    findByCpf:    (cpf) => ensure().clientes.lista.find(c => c.cpf === cpf) ?? null,
  },

  matches: {
    lista:         () => ensure().matches.lista,
    rankingFundos: () => ensure().matches.ranking_fundos,
    byCpf:         (cpf) => ensure().matches.lista.filter(m => m.cpf === cpf),
  },

  credit: {
    stats:    () => ensure().credit.stats,
    empresas: () => ensure().credit.empresas,
  },
};
