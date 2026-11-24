/**
 * Single Source of Truth Version Store (Frontend)
 * Carrega a versão e metadados do sistema dinamicamente a partir do Backend (/api/health).
 * Você SÓ PRECISA alterar a versão no arquivo backend 'src/version.py'.
 */
import { ref } from 'vue';

export const APP_VERSION = ref('');
export const APP_NAME = ref('TraceOPME');
export const SYSTEM_TITLE = ref('TraceOPME');
export const SUBTITLE = ref('Rastreabilidade de OPME — do almoxarifado ao paciente');
export const AUTHOR = ref('Camila Corrêa de Melo');
// E-mail de contato do suporte (rodapé do login e do menu).
export const SUPPORT_EMAIL = 'camila.melo.3@hubrasil.gov.br';
export const HOSPITAL_NAME = ref('Hospital das Clínicas da UFPE (HC-UFPE / EBSERH)');
export const DEPARTMENT_NAME = ref('Escritório de Processos');

export async function fetchSystemConfig() {
  try {
    // v18.12: fetch direto (sem o axios da aplicação) — a importação circular com
    // services/api fazia esta chamada falhar em silêncio e o rodapé ficava preso
    // numa versão antiga ("18.9.0").
    const r = await fetch('/api/health', { cache: 'no-store' });
    const response = { data: await r.json() };
    if (response.data) {
      if (response.data.version) APP_VERSION.value = response.data.version;
      if (response.data.app_name) APP_NAME.value = response.data.app_name;
      if (response.data.system_title) SYSTEM_TITLE.value = response.data.system_title;
      if (response.data.subtitle) SUBTITLE.value = response.data.subtitle;
      if (response.data.author) AUTHOR.value = response.data.author;
      if (response.data.organization) HOSPITAL_NAME.value = response.data.organization;
      if (response.data.department) DEPARTMENT_NAME.value = response.data.department;
    }
  } catch (error) {
    // Mantém fallbacks caso a API ainda esteja iniciando
  }
}

// Inicialização automática ao carregar o frontend
fetchSystemConfig();
