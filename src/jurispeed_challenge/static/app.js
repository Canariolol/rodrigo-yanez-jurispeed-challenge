import { createApp, nextTick } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";

const app = createApp({
  data() {
    return {
      draft: "",
      errorMessage: "",
      loading: false,
      messages: [],
      sessionId: "",
      lastToolCalls: [],
      lastActivities: [],
      currentProcessingIndex: 0,
      processingTimerId: null,
      processingSteps: [
        {
          key: "orchestrator-analysis",
          label: "Orquestador",
          color: "#6366f1",
          detail: "analizando consulta",
        },
        {
          key: "litigante-search",
          label: "Litigante",
          color: "#3b82f6",
          detail: "buscando jurisprudencia",
        },
        {
          key: "normativo-search",
          label: "Normativo",
          color: "#f59e0b",
          detail: "buscando normativa",
        },
        {
          key: "orchestrator-synthesis",
          label: "Orquestador",
          color: "#6366f1",
          detail: "sintetizando respuesta",
        },
      ],
    };
  },
  computed: {
    activeProcessingStep() {
      return this.processingSteps[this.currentProcessingIndex] || this.processingSteps[0];
    },
  },
  async mounted() {
    await this.fetchState();
  },
  methods: {
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
        this.errorMessage = error.message || "Ocurrio un error inesperado.";
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
        this.errorMessage = error.message || "No fue posible reiniciar la conversacion.";
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
          content: "El orquestador esta procesando tu consulta...",
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
    renderMessage(content) {
      if (typeof content === "string") {
        return content;
      }
      return JSON.stringify(content, null, 2);
    },
    messageLabel(message) {
      if (message.role === "user") {
        return "Usuario";
      }
      return "Orquestador";
    },
    messageCardClass(message) {
      if (message.pending) {
        return "assistant-message pending-message";
      }
      return message.role === "user" ? "user-message" : "assistant-message";
    },
    messageAgentStyle(message) {
      const color = message.role === "user" ? "#2563eb" : "#6366f1";
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
