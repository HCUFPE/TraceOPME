<template>
  <div>
    <a :class="['acao-card', 'cor-amarelo', { alta: d.chamados_abertos }]" href="/chamados" style="display:block;margin-bottom:1rem">
      <h3>Chamados — problemas reportados</h3>
      <div class="numero">{{ d.chamados_abertos || 0 }}</div>
      <p class="rotulo">chamado(s) aberto(s) ou em andamento. Os usuários abrem pelo botão “Reportar problema”, no topo da tela.</p>
    </a>
    <!-- v18.4: cópia diária + cópia fora do servidor -->
    <div class="cartao" :style="`border-left:5px solid var(${b.tudo_certo ? '--verde' : '--vermelho'})`">
      <div class="entre">
        <h2>Cópia de segurança</h2>
        <form method="post" action="/admin/backup" style="margin:0">
          <button class="botao secundario pequeno">Gerar cópia agora (e enviar para a rede)</button>
        </form>
      </div>
      <p class="pequeno" style="margin:.2rem 0 .6rem">O sistema faz uma cópia <strong>todo dia às {{ b.hora }}</strong>, confere se ela abre
        e está íntegra e envia uma segunda cópia para a pasta de rede, fora do servidor.</p>
      <div class="backup-grade">
        <div :class="['bk', b.em_dia ? 'bk-ok' : 'bk-erro']">
          <div class="bk-tit">1. Cópia no servidor</div>
          <template v-if="b.ultima">
            <div><strong>{{ f.dataHoraBr(b.ultima.quando) }}</strong> · {{ b.ultima.tamanho_mb }} MB</div>
            <div class="pequeno">{{ b.conferencia || 'conferida' }} · {{ b.total }} cópia(s) guardada(s)</div>
          </template>
          <div v-else>Nenhuma cópia ainda.</div>
          <div v-if="b.erro_local" class="pequeno erro-txt">Última tentativa falhou: {{ b.erro_local }}</div>
          <div v-else-if="!b.opme_em_dia && b.ultima" class="pequeno erro-txt">A última cópia é de {{ b.dias_desde_ultima }} dia(s) atrás.</div>
          <div class="pequeno">Inclui o banco administrativo (app.db)<template v-if="b.app_ultima">: {{ f.dataHoraBr(b.app_ultima) }}</template>.</div>
          <div v-if="b.app_erro" class="pequeno erro-txt">app.db: {{ b.app_erro }}</div>
          <div v-else-if="b.app_esperado && !b.app_em_dia" class="pequeno erro-txt">app.db sem cópia conferida de hoje — o sistema tenta de novo a cada 30 min.</div>
          <div class="pequeno suave mono">{{ b.pasta }}</div>
        </div>
        <div :class="['bk', b.externo_em_dia ? 'bk-ok' : 'bk-erro']">
          <div class="bk-tit">2. Cópia fora do servidor (rede)</div>
          <template v-if="!b.externa_configurada">
            <div><strong>Não configurada — os dados NÃO estão protegidos fora do servidor.</strong></div>
            <div class="pequeno">Peça à TI uma pasta de rede e coloque o caminho em <span class="mono">BACKUP_PASTA_EXTERNA</span>
              no arquivo <span class="mono">.env</span> do servidor; depois reinicie o TraceOPME.</div>
          </template>
          <template v-else>
            <div v-if="b.externo_ultima"><strong>{{ f.dataHoraBr(b.externo_ultima) }}</strong></div>
            <div v-else>Ainda não enviada.</div>
            <div v-if="b.externo_erro" class="pequeno erro-txt">Falhou: {{ b.externo_erro }} — o sistema tenta de novo a cada 30 min.</div>
            <div class="pequeno suave mono">{{ b.pasta_externa }}</div>
          </template>
        </div>
      </div>
    </div>

    <div class="cabecalho-pagina">
      <div>
        <h1>Administração</h1>
        <p>Liberação de acesso, perfis e redefinição de senha.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/admin/entrega-paciente">Materiais com entrega da caixa ao paciente</a>
        <a class="botao secundario" href="/indicadores/metas"> Metas dos indicadores</a>
        <a class="botao secundario" href="/admin/diagnostico"> Diagnóstico técnico</a>
      </div>
    </div>

    <!-- Framework SETISD: inclusão direta, validando o login no Active Directory. -->
    <div class="cartao" id="incluir-usuario" style="border-left:5px solid var(--azul)">
      <h2>Incluir usuário</h2>
      <p class="suave pequeno" style="margin-top:0">
        <template v-if="modoAd">Digite o login de rede e clique em <strong>Consultar AD</strong>: nome, e-mail e
          setor vêm do Active Directory. Depois escolha o perfil de acesso. A senha é a da rede.</template>
        <template v-else>O AD não está configurado neste servidor: o acesso usa a senha local. Informe os dados
          e uma senha inicial (mínimo 8 caracteres, com letras e números).</template>
      </p>
      <form @submit.prevent="incluir" data-local="1" autocomplete="off">
        <div class="grade grade-3">
          <div class="campo">
            <label class="obrigatorio">Login de rede</label>
            <div style="display:flex;gap:.4rem">
              <input type="text" v-model="novo.username" required autocomplete="off" @input="consulta = null">
              <button v-if="modoAd" type="button" class="botao secundario" style="white-space:nowrap" :disabled="!novo.username.trim() || consultando" @click="consultarAd">
                {{ consultando ? 'Consultando…' : 'Consultar AD' }}</button>
            </div>
          </div>
          <div class="campo"><label class="obrigatorio">Nome completo</label>
            <input type="text" v-model="novo.nome" required :readonly="modoAd && !!consulta?.exists"></div>
          <div class="campo"><label>E-mail</label>
            <input type="email" v-model="novo.email" :readonly="modoAd && !!consulta?.exists"></div>
          <div class="campo"><label>Setor</label>
            <input type="text" v-model="novo.setor" :readonly="modoAd && !!consulta?.exists && !!consulta?.department"></div>
          <div class="campo"><label class="obrigatorio">Perfil de acesso</label>
            <select v-model="novo.papel" required>
              <option value="">— escolha —</option>
              <option v-for="(dados, codigo) in d.papeis" :key="codigo" :value="codigo">{{ dados[0] }}</option>
            </select></div>
          <div v-if="!modoAd" class="campo"><label class="obrigatorio">Senha inicial</label>
            <input type="password" v-model="novo.senha" required autocomplete="new-password"></div>
        </div>
        <div v-if="consulta" :class="['aviso', consulta.exists && !consulta.ja_cadastrado ? 'sucesso' : 'erro']" style="margin:.4rem 0">
          <template v-if="!consulta.exists">Login <strong>{{ consulta.username }}</strong> não encontrado no AD.</template>
          <template v-else-if="consulta.ja_cadastrado">{{ consulta.displayName }} já tem acesso ao TraceOPME — altere o perfil na lista abaixo.</template>
          <template v-else>Encontrado no AD: <strong>{{ consulta.displayName }}</strong><template v-if="consulta.department"> · {{ consulta.department }}</template>.</template>
        </div>
        <button class="botao" :disabled="enviando || (modoAd && !(consulta?.exists && !consulta?.ja_cadastrado))">Incluir usuário</button>
      </form>
    </div>

    <!-- Catálogo de materiais do hospital: é dele que vem a descrição "HC - …" que
         aparece ao digitar o código AGHU no almoxarifado. -->
    <div class="cartao" style="border-left:5px solid var(--azul)">
      <h2>Lista de materiais do hospital (códigos AGHU)</h2>
      <p class="suave pequeno" style="margin-top:0">
        É daqui que vem a descrição <strong>HC -</strong> que aparece ao digitar o
        código AGHU no almoxarifado.
        <template v-if="d.catalogo?.total">
          Hoje: <strong>{{ d.catalogo.total }}</strong> códigos, atualizados por último em
          {{ f.dataHoraBr(d.catalogo.quando) }}<template v-if="d.catalogo.quem"> por {{ d.catalogo.quem }}</template>.
        </template>
        <template v-else>Ainda não há nenhum código carregado.</template>
      </p>
      <form method="post" action="/admin/materiais" enctype="multipart/form-data"
            data-confirmar="Atualizar a lista de materiais com esta planilha?">
        <div class="filtros">
          <div class="campo" style="flex:1">
            <label class="obrigatorio">Planilha atualizada (.xlsx ou .csv)</label>
            <input type="file" name="arquivo" accept=".xlsx,.csv" required>
          </div>
          <button class="botao">Atualizar lista</button>
        </div>
        <p class="suave pequeno" style="margin:.4rem 0 0">
          Use o arquivo como ele sai da MasterTools — as colunas são reconhecidas pelo
          nome (“Código AGHU”, “Nome Material”, “Valor Unitário”, “Código Master”), em
          qualquer ordem. Códigos novos entram, os que mudaram são atualizados, e os que
          saíram da planilha <strong>continuam</strong> no sistema. Materiais que já deram
          entrada guardam a descrição que tinham na época.
        </p>
        <p class="suave pequeno" style="margin:.4rem 0 0">
          <strong>Código master (v18):</strong> também aceita uma planilha só com a relação
          “Código AGHU” → “Código master” (duas colunas, sem o nome). Ela só preenche o código master
          dos materiais que já estão na lista — é o código que o robô usa para lançar a NF no AGHU.
        </p>
      </form>

      <template v-if="r">
        <div v-if="r.relacao_master" class="grade grade-4" style="margin-top:1rem">
          <div class="cartao"><div class="rotulo">código master preenchido</div><div class="numero">{{ r.alterados }}</div></div>
          <div class="cartao"><div class="rotulo">já estavam certos</div><div class="numero">{{ r.iguais }}</div></div>
          <div class="cartao"><div class="rotulo">AGHU fora da lista</div><div class="numero">{{ r.fora_do_catalogo }}</div></div>
          <div class="cartao"><div class="rotulo">linhas ignoradas</div><div class="numero">{{ r.ignoradas }}</div></div>
        </div>
        <p v-if="r.exemplos_fora?.length" class="pequeno suave">Exemplos de AGHU fora da lista:
          <span class="mono">{{ r.exemplos_fora.join(', ') }}</span></p>
        <div v-if="!r.relacao_master" class="grade grade-4" style="margin-top:1rem">
          <div class="cartao"><div class="rotulo">códigos novos</div><div class="numero">{{ r.novos }}</div></div>
          <div class="cartao"><div class="rotulo">alterados</div><div class="numero">{{ r.alterados }}</div></div>
          <div class="cartao"><div class="rotulo">sem mudança</div><div class="numero">{{ r.iguais }}</div></div>
          <div class="cartao"><div class="rotulo">fora da planilha (mantidos)</div><div class="numero">{{ r.ausentes }}</div></div>
        </div>
        <p class="pequeno suave">
          {{ r.lidos }} código(s) lido(s) de <span class="mono">{{ r.arquivo }}</span>.
          <template v-if="r.ignoradas">{{ r.ignoradas }} linha(s) sem código AGHU ou sem nome foram ignoradas.</template>
        </p>
        <template v-if="r.exemplos?.length">
          <p class="pequeno" style="margin-bottom:.3rem"><strong>Exemplos do que mudou:</strong></p>
          <ul class="pequeno" style="margin-top:0">
            <li v-for="(e, n) in r.exemplos" :key="n"><span class="mono">{{ e.codigo }}</span>: “{{ e.antes }}” → “{{ e.depois }}”</li>
          </ul>
        </template>
      </template>
    </div>

    <div class="cartao">
      <h2>Solicitações pendentes ({{ d.solicitacoes.length }})</h2>
      <div v-if="d.solicitacoes.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Tipo</th><th>Usuário</th><th>Nome</th><th>Setor</th><th>Solicitada em</th><th>Ações</th></tr></thead>
          <tbody>
            <tr v-for="s in d.solicitacoes" :key="s.id_solicitacao">
              <td><span :class="['etiqueta', s.tipo === 'cadastro' ? 'azul' : 'amarelo']">{{ s.tipo === 'cadastro' ? 'Novo acesso' : 'Nova senha' }}</span></td>
              <td class="mono">{{ s.username }}</td>
              <td>{{ s.nome || '—' }}<br><span class="suave pequeno">{{ s.email || '' }}</span>
                <template v-if="s.observacao"><br><span class="etiqueta azul pequeno">{{ s.observacao }}</span></template></td>
              <td>{{ s.setor || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(s.criada_em) }}</td>
              <td>
                <form method="post" :action="`/admin/solicitacao/${s.id_solicitacao}/aprovar`"
                      style="display:flex;gap:.4rem;align-items:center;margin-bottom:.4rem">
                  <select v-if="s.tipo === 'cadastro'" name="papel" style="width:auto">
                    <option v-for="(dados, codigo) in d.papeis" :key="codigo" :value="codigo" :selected="s.papel === codigo">{{ dados[0] }}</option>
                  </select>
                  <button class="botao pequeno">Aprovar</button>
                </form>
                <form method="post" :action="`/admin/solicitacao/${s.id_solicitacao}/rejeitar`"
                      style="display:flex;gap:.4rem" data-confirmar="Rejeitar esta solicitação?">
                  <input type="text" name="motivo" placeholder="motivo" style="width:auto">
                  <button class="botao pequeno secundario">Rejeitar</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma solicitação pendente.</p>
    </div>

    <div class="cartao">
      <h2>Usuários ({{ d.usuarios.length }})</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Usuário</th><th>Nome</th><th>Setor</th><th>Perfil</th>
                     <th>Situação</th><th>Último acesso</th><th>Ações</th></tr></thead>
          <tbody>
            <tr v-for="u in d.usuarios" :key="u.username">
              <td class="mono">{{ u.username }}</td>
              <td>{{ u.nome }}<br><span class="suave pequeno">{{ u.email || '' }}</span></td>
              <td>{{ u.setor || '—' }}</td>
              <td>
                <form method="post" :action="`/admin/usuario/${u.username}/papel`" style="display:flex;gap:.4rem">
                  <select name="papel" style="width:auto">
                    <option v-for="(dados, codigo) in d.papeis" :key="codigo" :value="codigo" :selected="u.papel === codigo">{{ dados[0] }}</option>
                  </select>
                  <button class="botao pequeno secundario">Salvar</button>
                </form>
              </td>
              <td><span :class="['etiqueta', u.status === 'ativo' ? 'verde' : 'cinza']">{{ u.status }}</span></td>
              <td class="pequeno">{{ f.dataHoraBr(u.ultimo_acesso) || 'nunca' }}
                <template v-if="u.bloqueado_ate">
                  <br><span class="etiqueta vermelho">bloqueado por tentativas</span>
                  <form method="post" :action="`/admin/usuarios/${u.username}/desbloquear`" style="display:inline">
                    <button class="botao pequeno secundario">Desbloquear</button>
                  </form>
                </template>
              </td>
              <td>
                <form method="post" :action="`/admin/usuario/${u.username}/status`">
                  <input type="hidden" name="status" :value="u.status === 'ativo' ? 'inativo' : 'ativo'">
                  <button :class="['botao', 'pequeno', { perigo: u.status === 'ativo' }]">{{ u.status === 'ativo' ? 'Desativar' : 'Ativar' }}</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, meta, avisos, pagina, getJson, postJson, mensagemDeErro } = useTela();
const b = computed(() => props.d.backup || {});
const r = computed(() => props.d.resultado_catalogo);
const modoAd = computed(() => meta.dados?.modo_autenticacao === 'ad');

const novo = reactive({ username: '', nome: '', email: '', setor: '', papel: '', senha: '' });
const consulta = ref<any>(null);
const consultando = ref(false);
const enviando = ref(false);

async function consultarAd() {
  const login = novo.username.trim();
  if (!login) return;
  consultando.value = true;
  try {
    const res: any = await getJson(`/api/admin/ad-user-search/${encodeURIComponent(login)}`);
    consulta.value = res;
    if (res.exists) {
      novo.username = res.username || login;
      novo.nome = res.displayName || '';
      novo.email = res.email || '';
      novo.setor = res.department || novo.setor;
    }
  } catch (e) {
    avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false);
  } finally {
    consultando.value = false;
  }
}

async function incluir() {
  enviando.value = true;
  try {
    const res: any = await postJson('/api/admin/usuarios', { ...novo, username: novo.username.trim() });
    avisos.mostrar({ texto: res.mensagem, tipo: 'sucesso' }, false);
    Object.assign(novo, { username: '', nome: '', email: '', setor: '', papel: '', senha: '' });
    consulta.value = null;
    await pagina.recarregar();
  } catch (e) {
    avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false);
  } finally {
    enviando.value = false;
  }
}
</script>

<style scoped>
.backup-grade { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: .7rem; }
.bk { border-radius: 10px; padding: .7rem .9rem; border: 1px solid; display: flex; flex-direction: column; gap: .2rem; }
.bk-ok { background: #eef9f2; border-color: #9fd3b4; } .bk-erro { background: #fdf1f0; border-color: #efb0aa; }
.bk-tit { font-weight: 700; } .erro-txt { color: #8e1c1c; font-weight: 600; }
</style>
