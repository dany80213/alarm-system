import smtplib
import logging
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

MODE_LABELS = {
    "ARMED_HOME": "Perimetrale",
    "ARMED_AWAY": "Completo",
}

ZONE_LABELS = {
    "perimeter": "Perimetrale",
    "internal":  "Interna",
}

TYPE_LABELS = {
    "door":       "Porta",
    "window":     "Finestra",
    "motion":     "Sensore PIR",
    "gate":       "Cancello",
    "controller": "Controller",
}


class EmailNotifier:
    def __init__(self, settings: dict):
        self._settings = settings

    # ── Configurazione live ────────────────────────────────────────────────────

    def _cfg(self) -> dict:
        return self._settings.get("notifications", {})

    def is_enabled(self) -> bool:
        return self._cfg().get("enabled", False)

    # ── Invio allarme (async, non blocca) ─────────────────────────────────────

    def send_alarm(self, device_name: str, mode: str, zone: str,
                   device_type: str, timestamp: float):
        if not self.is_enabled():
            return
        threading.Thread(
            target=self._do_send_alarm,
            args=(device_name, mode, zone, device_type, timestamp),
            daemon=True,
        ).start()

    def _do_send_alarm(self, device_name, mode, zone, device_type, timestamp):
        cfg = self._cfg()
        recipients = cfg.get("recipients", [])
        if not recipients:
            logger.warning("Notifica allarme: nessun destinatario configurato")
            return

        dt       = datetime.fromtimestamp(timestamp)
        ora      = dt.strftime("%H:%M:%S")
        data     = dt.strftime("%d/%m/%Y")
        mode_lbl = MODE_LABELS.get(mode, mode)
        zone_lbl = ZONE_LABELS.get(zone, zone)
        type_lbl = TYPE_LABELS.get(device_type, device_type)

        try:
            tpl = (TEMPLATES_DIR / "email_allarme.html").read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Errore lettura template email_allarme.html: {e}")
            return

        html = (tpl
                .replace("{{DEVICE}}", device_name)
                .replace("{{MODE}}",   mode_lbl)
                .replace("{{ZONE}}",   zone_lbl)
                .replace("{{TYPE}}",   type_lbl)
                .replace("{{ORA}}",    ora)
                .replace("{{DATA}}",   data))

        self._send(cfg.get("smtp", {}), recipients,
                   "[ALLARME] Sistema di sicurezza attivato", html)

    # ── Invio email di test (sync, ritorna esito) ──────────────────────────────

    def send_test(self) -> tuple[bool, str]:
        cfg        = self._cfg()
        recipients = cfg.get("recipients", [])
        if not recipients:
            return False, "Nessun destinatario configurato"

        dt   = datetime.now()
        ora  = dt.strftime("%H:%M:%S")
        data = dt.strftime("%d/%m/%Y")

        try:
            tpl = (TEMPLATES_DIR / "email_test.html").read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Errore template: {e}"

        html = tpl.replace("{{ORA}}", ora).replace("{{DATA}}", data)
        return self._send(cfg.get("smtp", {}), recipients,
                          "[TEST] Sistema di sicurezza — Email di prova", html)

    # ── Helper SMTP ────────────────────────────────────────────────────────────

    def _send(self, smtp_cfg: dict, recipients: list, subject: str,
              html: str) -> tuple[bool, str]:
        host      = smtp_cfg.get("host", "").strip()
        port      = int(smtp_cfg.get("port", 587))
        user      = smtp_cfg.get("user", "").strip()
        password  = smtp_cfg.get("password", "")
        from_addr = smtp_cfg.get("from_addr", "").strip() or user
        use_tls   = smtp_cfg.get("use_tls", True)

        if not host:
            return False, "Host SMTP non configurato"
        if not recipients:
            return False, "Nessun destinatario"

        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(host, port, timeout=15)

            if user and password:
                server.login(user, password)

            server.sendmail(from_addr, recipients, msg.as_string())
            server.quit()
            logger.info(f"Email inviata a {recipients}: {subject}")
            return True, "OK"
        except Exception as e:
            logger.error(f"Errore invio email: {e}")
            return False, str(e)
