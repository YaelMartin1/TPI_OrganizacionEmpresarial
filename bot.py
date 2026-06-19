import csv
import os
import datetime
import uuid
from enum import Enum, auto


# CONFIGURACION / "PLANTILLA" DE BASE DE DATOS

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
PRESUPUESTO_FILE = os.path.join(DB_DIR, "presupuesto.csv")
GASTOS_FILE = os.path.join(DB_DIR, "gastos.csv")
ESTADO_FILE = os.path.join(DB_DIR, "estado_usuario.csv")

CATEGORIAS_VALIDAS = ["Alojamiento", "Transporte", "Comidas", "Varios"]


def asegurar_db():
    """Crea la carpeta db/ y los CSV con encabezados si no existen.
    Si no hay un viaje activo, crea uno de ejemplo con presupuesto inicial."""
    os.makedirs(DB_DIR, exist_ok=True)

    if not os.path.exists(PRESUPUESTO_FILE):
        with open(PRESUPUESTO_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["viaje_id", "gerente", "presupuesto_total", "saldo_disponible", "estado_viaje"])
            w.writerow(["VIAJE-0001", "Gerente Demo", "100000", "100000", "ABIERTO"])

    if not os.path.exists(GASTOS_FILE):
        with open(GASTOS_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["gasto_id", "viaje_id", "fecha", "monto", "categoria",
                        "tiene_factura", "estado_aprobacion", "tipo_aprobacion"])

    if not os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["usuario", "estado", "gasto_temporal"])


def leer_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir_csv(path, filas, columnas):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)


def agregar_fila_csv(path, fila, columnas):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writerow(fila)


# MAQUINA DE ESTADOS

class Estado(Enum):
    INICIO = auto()
    ESPERANDO_FECHA = auto()
    ESPERANDO_MONTO = auto()
    ESPERANDO_CATEGORIA = auto()
    ESPERANDO_FACTURA = auto()
    ESPERANDO_DECISION_EXCEPCION = auto()
    ESPERANDO_JUSTIFICATIVO = auto()
    ESPERANDO_APROBACION_DIRECTOR = auto()
    MENU_VIAJE_FINALIZADO = auto()
    FIN = auto()


class GastoBot:
    """Implementa el flujo TO-BE del BPMN para un usuario (gerente/director)."""

    def __init__(self, usuario, viaje_id="VIAJE-0001"):
        self.usuario = usuario
        self.viaje_id = viaje_id
        self.estado = Estado.INICIO
        self.gasto_temp = {}  
        self._cargar_estado_persistido()

    # Persistencia de estado

    def _cargar_estado_persistido(self):
        filas = leer_csv(ESTADO_FILE)
        for f in filas:
            if f["usuario"] == self.usuario:
                self.estado = Estado[f["estado"]]
                return
        # si no existe, se crea registro inicial
        self._guardar_estado()

    def _guardar_estado(self):
        filas = leer_csv(ESTADO_FILE)
        filas = [f for f in filas if f["usuario"] != self.usuario]
        filas.append({
            "usuario": self.usuario,
            "estado": self.estado.name,
            "gasto_temporal": str(self.gasto_temp),
        })
        escribir_csv(ESTADO_FILE, filas, ["usuario", "estado", "gasto_temporal"])

    # Helpers de negocio

    def _obtener_viaje(self):
        for f in leer_csv(PRESUPUESTO_FILE):
            if f["viaje_id"] == self.viaje_id:
                return f
        return None

    def _actualizar_saldo(self, monto_a_descontar):
        filas = leer_csv(PRESUPUESTO_FILE)
        for f in filas:
            if f["viaje_id"] == self.viaje_id:
                f["saldo_disponible"] = str(float(f["saldo_disponible"]) - monto_a_descontar)
        escribir_csv(PRESUPUESTO_FILE, filas, ["viaje_id", "gerente", "presupuesto_total",
                                                "saldo_disponible", "estado_viaje"])

    def _registrar_gasto(self, estado_aprobacion, tipo_aprobacion):
        gasto_id = "G-" + uuid.uuid4().hex[:6].upper()
        fila = {
            "gasto_id": gasto_id,
            "viaje_id": self.viaje_id,
            "fecha": self.gasto_temp["fecha"],
            "monto": self.gasto_temp["monto"],
            "categoria": self.gasto_temp["categoria"],
            "tiene_factura": self.gasto_temp["tiene_factura"],
            "estado_aprobacion": estado_aprobacion,
            "tipo_aprobacion": tipo_aprobacion,
        }
        agregar_fila_csv(GASTOS_FILE, fila,
                          ["gasto_id", "viaje_id", "fecha", "monto", "categoria",
                           "tiene_factura", "estado_aprobacion", "tipo_aprobacion"])
        return gasto_id

    # Motor principal: 1 mensaje del usuario -> 1 respuesta del bot

    def procesar(self, mensaje):
        mensaje = mensaje.strip()

        # comandos globales, disponibles en cualquier estado (camino infeliz / atajos)
        if mensaje.lower() in ("/saldo", "saldo"):
            viaje = self._obtener_viaje()
            return f"Saldo disponible del viaje {self.viaje_id}: ${viaje['saldo_disponible']}"

        if mensaje.lower() in ("/cancelar", "cancelar"):
            self.gasto_temp = {}
            self.estado = Estado.INICIO
            self._guardar_estado()
            return "Carga cancelada. Volviste al inicio. Escribi 'gasto' para cargar uno nuevo."

        if mensaje.lower() in ("/ayuda", "ayuda", "/help"):
            return ("Comandos disponibles:\n"
                    "  gasto        -> iniciar la carga de un nuevo gasto\n"
                    "  saldo        -> ver presupuesto disponible del viaje\n"
                    "  cancelar     -> cancelar la carga en curso\n"
                    "  finalizar viaje -> cerrar el viaje y enviar a aprobacion final")

        # Maquina de estados

        if self.estado == Estado.INICIO:
            if mensaje.lower() == "gasto":
                self.estado = Estado.ESPERANDO_FECHA
                self._guardar_estado()
                return "Perfecto, vamos a cargar un gasto. Decime la FECHA (DD/MM/AAAA):"
            if mensaje.lower() == "finalizar viaje":
                self.estado = Estado.MENU_VIAJE_FINALIZADO
                self._guardar_estado()
                viaje = self._obtener_viaje()
                return (f"Viaje {self.viaje_id} congelado. Dashboard final enviado al director "
                        f"para aprobacion. Saldo final: ${viaje['saldo_disponible']}.")
            return "No entendi. Escribi 'gasto' para cargar un gasto, o 'ayuda' para ver comandos."

        if self.estado == Estado.ESPERANDO_FECHA:
            try:
                fecha = datetime.datetime.strptime(mensaje, "%d/%m/%Y").date()
                hoy = datetime.date.today()
                if fecha > hoy:
                    return "Esa fecha es futura. Mandame la fecha real en que ocurrio el gasto (DD/MM/AAAA):"
                self.gasto_temp["fecha"] = mensaje
                self.estado = Estado.ESPERANDO_MONTO
                self._guardar_estado()
                return "Listo. Ahora decime el MONTO del gasto (solo numeros, ej: 4500):"
            except ValueError:
                # CAMINO INFELIZ: formato de fecha invalido
                return ("Esa fecha no es valida. Usa el formato DD/MM/AAAA "
                        "(ej: 15/03/2026). Probemos de nuevo:")

        if self.estado == Estado.ESPERANDO_MONTO:
            try:
                monto = float(mensaje.replace(",", "."))
                if monto <= 0:
                    return "El monto tiene que ser mayor a cero. Decime el monto del gasto:"
                self.gasto_temp["monto"] = monto
                self.estado = Estado.ESPERANDO_CATEGORIA
                self._guardar_estado()
                return ("Categorias validas: " + ", ".join(CATEGORIAS_VALIDAS) +
                        ".\nEscribi la categoria del gasto:")
            except ValueError:
                # CAMINO INFELIZ: el usuario mando texto en vez de numero
                return "Eso no es un numero valido. Mandame solo el monto, ej: 4500"

        if self.estado == Estado.ESPERANDO_CATEGORIA:
            categoria = mensaje.strip().capitalize()
            if categoria not in CATEGORIAS_VALIDAS:
                # CAMINO INFELIZ: categoria inexistente / no aprobada
                return (f"'{mensaje}' no es una categoria aprobada. "
                        f"Opciones validas: {', '.join(CATEGORIAS_VALIDAS)}. Intenta de nuevo:")
            self.gasto_temp["categoria"] = categoria
            self.estado = Estado.ESPERANDO_FACTURA
            self._guardar_estado()
            return "¿Tenes la factura o comprobante? (si/no)"

        if self.estado == Estado.ESPERANDO_FACTURA:
            resp = mensaje.lower()
            if resp not in ("si", "no"):
                return "Respondeme 'si' o 'no': ¿tenes la factura?"
            if resp == "no":
                # CAMINO INFELIZ: intento de registrar un gasto sin factura
                return ("No se puede registrar un gasto sin comprobante. "
                        "Conseguila y volve a intentar, o escribi 'cancelar'.")
            self.gasto_temp["tiene_factura"] = "si"
            return self._validar_presupuesto()

        if self.estado == Estado.ESPERANDO_DECISION_EXCEPCION:
            resp = mensaje.lower()
            if resp not in ("si", "no"):
                return "Respondeme 'si' o 'no': ¿queres solicitar aprobacion extraordinaria?"
            if resp == "no":
                gasto_id = self._registrar_gasto("RECHAZADO", "NORMAL")
                self.estado = Estado.INICIO
                self.gasto_temp = {}
                self._guardar_estado()
                return f"Gasto {gasto_id} marcado como RECHAZADO (excede presupuesto, sin excepcion solicitada)."
            self.estado = Estado.ESPERANDO_JUSTIFICATIVO
            self._guardar_estado()
            return "Escribi brevemente el justificativo para el director:"

        if self.estado == Estado.ESPERANDO_JUSTIFICATIVO:
            self.gasto_temp["justificativo"] = mensaje
            self.estado = Estado.ESPERANDO_APROBACION_DIRECTOR
            self._guardar_estado()
            return ("Solicitud enviada al director con el justificativo. "
                     "[SIMULACION] Escribi 'aprobar' o 'rechazar' como si fueras el director:")

        if self.estado == Estado.ESPERANDO_APROBACION_DIRECTOR:
            resp = mensaje.lower()
            if resp not in ("aprobar", "rechazar"):
                # CAMINO INFELIZ: respuesta de aprobacion ambigua
                return "Respuesta no reconocida. El director debe escribir 'aprobar' o 'rechazar':"
            if resp == "rechazar":
                gasto_id = self._registrar_gasto("RECHAZADO", "EXTRAORDINARIO_RECHAZADO")
                self.estado = Estado.INICIO
                self.gasto_temp = {}
                self._guardar_estado()
                return f"Gasto {gasto_id} RECHAZADO por el director."
            monto = self.gasto_temp["monto"]
            self._actualizar_saldo(monto)
            gasto_id = self._registrar_gasto("APROBADO", "EXTRAORDINARIO")
            self.estado = Estado.INICIO
            self.gasto_temp = {}
            self._guardar_estado()
            return (f"Gasto {gasto_id} APROBADO como EXTRAORDINARIO por el director. "
                     "Se registro en la base y se actualizo el dashboard de finanzas.")

        if self.estado == Estado.MENU_VIAJE_FINALIZADO:
            if mensaje.lower() in ("aprobar", "si"):
                self.estado = Estado.FIN
                self._guardar_estado()
                return "Director aprobo la rendicion final. Finanzas registra el cierre. Viaje rendido. FIN."
            if mensaje.lower() in ("rechazar", "no"):
                return "Director rechazo la rendicion final. Se devuelve al gerente para revision."
            return "El viaje ya esta finalizado y esperando aprobacion final. Escribi 'aprobar' o 'rechazar' (simulando al director):"

        if self.estado == Estado.FIN:
            return "El viaje ya fue rendido y cerrado. Gracias."

        return "No entendi tu mensaje. Escribi 'ayuda' para ver las opciones."

    # Logica de validacion automatica de presupuesto

    def _validar_presupuesto(self):
        viaje = self._obtener_viaje()
        saldo = float(viaje["saldo_disponible"])
        monto = self.gasto_temp["monto"]

        if monto <= saldo:
            categoria = self.gasto_temp.get("categoria", "")
            self._actualizar_saldo(monto)
            gasto_id = self._registrar_gasto("PREAPROBADO", "NORMAL")
            self.estado = Estado.INICIO
            self.gasto_temp = {}
            self._guardar_estado()
            return (f"Gasto {gasto_id} PRE-APROBADO automaticamente ✅\n"
                    f"Categoria: {categoria} | Monto: ${monto}\n"
                    f"Se registro en la base temporal del viaje y se notifico a Finanzas.")
        else:
            # CAMINO INFELIZ / regla de negocio: el gasto excede el presupuesto
            self.estado = Estado.ESPERANDO_DECISION_EXCEPCION
            self._guardar_estado()
            return (f"⚠️ Este gasto (${monto}) supera el saldo disponible (${saldo}). "
                     "No entra en la pre-aprobacion automatica.\n"
                     "¿Queres solicitar una aprobacion EXTRAORDINARIA al director? (si/no)")


# LOOP DE CONSOLA (simulación de conversacion de Telegram)

def main():
    asegurar_db()
    print("=" * 70)
    print(" BOT DE RENDICION DE GASTOS DE VIAJE (simulador) ")
    print("=" * 70)
    usuario = input("Nombre de usuario (simula tu chat_id de Telegram): ").strip() or "demo_user"
    bot = GastoBot(usuario)

    print("\nBot: Hola! Soy el bot de rendicion de gastos. Escribi 'ayuda' para ver "
          "los comandos, o 'gasto' para cargar uno. ('salir' para cerrar la app)\n")

    while True:
        try:
            mensaje = input(f"{usuario}: ")
        except (EOFError, KeyboardInterrupt):
            print("\nSesion cerrada.")
            break

        if mensaje.lower() == "salir":
            print("Bot: Listo, tu progreso quedo guardado. Nos vemos!")
            break

        respuesta = bot.procesar(mensaje)
        print(f"Bot: {respuesta}\n")


if __name__ == "__main__":
    main()
