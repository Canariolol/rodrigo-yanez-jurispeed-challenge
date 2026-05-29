import { createApp, nextTick } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";

const app = createApp({
  data() {
    return {
      // Modo activo: 'consulta' (LLM real) o 'tests' (pytest local).
      mode: "consulta",
      modeItems: [
        { value: "consulta", label: "Consulta", sub: "LLM en vivo", accent: "#6366f1" },
        { value: "tests", label: "Tests", sub: "pytest local", accent: "#f59e0b" },
      ],

      // --- Estado del chat ---
      draft: "",
      errorMessage: "",
      loading: false,
      messages: [],
      sessionId: "",
      lastToolCalls: [],
      lastActivities: [],
      currentProcessingIndex: 0,
      processingTimerId: null,
      theme: "dark",
      processingSteps: [
        { key: "orchestrator-analysis", label: "Orquestador", color: "#6366f1", detail: "analizando consulta" },
        { key: "litigante-search", label: "Litigante", color: "#3b82f6", detail: "buscando jurisprudencia" },
        { key: "normativo-search", label: "Normativo", color: "#f59e0b", detail: "buscando normativa" },
        { key: "orchestrator-synthesis", label: "Orquestador", color: "#6366f1", detail: "sintetizando respuesta" },
      ],

      // --- Estado del banco de pruebas ---
      testDetail: "classic",
      detailOptions: [
        { value: "simple", label: "Simple", flag: "--simple" },
        { value: "classic", label: "Classic", flag: "-v" },
        { value: "full", label: "Full", flag: "--full" },
      ],
      testRunning: false,
      testResult: null,
      testError: "",
    };
  },
  computed: {
    activeProcessingStep() {
      return this.processingSteps[this.currentProcessingIndex] || this.processingSteps[0];
    },
    consoleText() {
      return this.testResult ? this.testResult.output : "";
    },
    consoleCommand() {
      if (this.testResult) {
        return `$ ${this.testResult.command}`;
      }
      const option = this.detailOptions.find((opt) => opt.value === this.testDetail);
      const flag = option && option.flag !== "-v" ? ` ${option.flag}` : "";
      return `$ pytest${flag}`;
    },
  },
  async mounted() {
    this.initializeTheme();
    await this.fetchState();
  },
  methods: {
    setMode(value) {
      if (this.loading || this.testRunning || this.mode === value) {
        return;
      }
      this.mode = value;
    },

    initializeTheme() {
      const savedTheme = window.localStorage.getItem("jurispeed-theme");
      this.theme = savedTheme || "dark";
      document.documentElement.setAttribute("data-theme", this.theme);
    },
    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", this.theme);
      window.localStorage.setItem("jurispeed-theme", this.theme);
    },

    async fetchState() {
      const response = await fetch("/api/state");
      const payload = await response.json();
      this.sessionId = payload.session_id || "";
      this.messages = payload.messages || [];
      await this.scrollToBottom();
    },
    async sendMessage() {
      const message = this.draft.trim();
      if (!message || this.loading) {
        return;
      }

      this.loading = true;
      this.errorMessage = "";
      this.draft = "";
      this.pushPendingMessages(message);
      this.startProcessingAnimation();

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "No fue posible procesar la consulta.");
        }
        this.sessionId = payload.session_id || "";
        this.messages = payload.messages || [];
        this.lastToolCalls = payload.assistant?.tool_calls || [];
        this.lastActivities = payload.assistant?.activities || [];
        await this.scrollToBottom();
      } catch (error) {
        this.errorMessage = error.message || "Ocurrió un error inesperado.";
        this.draft = message;
        this.removePendingAssistantMessage();
      } finally {
        this.stopProcessingAnimation();
        this.loading = false;
      }
    },
    async resetSession() {
      if (this.loading) {
        return;
      }
      this.loading = true;
      this.errorMessage = "";
      try {
        await fetch("/api/session/reset", { method: "POST" });
        this.messages = [];
        this.lastToolCalls = [];
        this.lastActivities = [];
        this.sessionId = "";
        this.draft = "";
      } catch (error) {
        this.errorMessage = error.message || "No fue posible reiniciar la conversación.";
      } finally {
        this.loading = false;
      }
    },
    pushPendingMessages(message) {
      const localId = `pending-${Date.now()}`;
      this.messages = [
        ...this.messages,
        { role: "user", content: message, localId: `${localId}-user` },
        {
          role: "assistant",
          content: "El orquestador está procesando tu consulta…",
          pending: true,
          localId: `${localId}-assistant`,
        },
      ];
      this.scrollToBottom();
    },
    removePendingAssistantMessage() {
      this.messages = this.messages.filter((message) => !message.pending);
    },
    startProcessingAnimation() {
      this.currentProcessingIndex = 0;
      this.processingTimerId = window.setInterval(() => {
        this.currentProcessingIndex =
          (this.currentProcessingIndex + 1) % this.processingSteps.length;
      }, 1200);
    },
    stopProcessingAnimation() {
      if (this.processingTimerId) {
        window.clearInterval(this.processingTimerId);
        this.processingTimerId = null;
      }
      this.currentProcessingIndex = 0;
    },

    // --- Banco de pruebas ---
    async runTests() {
      if (this.testRunning) {
        return;
      }
      this.testRunning = true;
      this.testError = "";
      try {
        const response = await fetch("/api/tests/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ detail: this.testDetail }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "No fue posible ejecutar los tests.");
        }
        this.testResult = payload;
      } catch (error) {
        this.testError = error.message || "Ocurrió un error al ejecutar los tests.";
        this.testResult = null;
      } finally {
        this.testRunning = false;
      }
    },

    renderMessage(content) {
      if (typeof content === "string") {
        return content;
      }
      return JSON.stringify(content, null, 2);
    },
    messageLabel(message) {
      return message.role === "user" ? "Usuario" : "Orquestador";
    },
    messageClass(message) {
      if (message.pending) {
        return "assistant pending";
      }
      return message.role === "user" ? "user" : "assistant";
    },
    messageAgentStyle(message) {
      const color = message.role === "user" ? "#3b82f6" : "#6366f1";
      return { "--agent-color": color };
    },
    async scrollToBottom() {
      await nextTick();
      const timeline = this.$refs.timeline;
      if (timeline) {
        timeline.scrollTop = timeline.scrollHeight;
      }
    },
  },
});

app.config.compilerOptions.delimiters = ["[[", "]]"];
app.mount("#app");
