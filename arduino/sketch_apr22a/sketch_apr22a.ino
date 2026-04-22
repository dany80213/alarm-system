#include <PubSubClient.h>
#include <WiFi.h>
#include <ArduinoJson.h>


// Replace the next variables with your SSID/Password combination
const char* ssid = "REPLACE_WITH_YOUR_SSID";
const char* password = "REPLACE_WITH_YOUR_PASSWORD";


const char* mqtt_server = "YOUR_MQTT_BROKER_IP_ADDRESS";

#define ALARM_PIN 4
#define ALARM_TOPIC "home/alarm/state"

WiFiClient espClient;
PubSubClient client(espClient);

void callback(char* topic, byte* message, unsigned int length) {
  // Assembla il payload in una stringa
  String payload;
  for (unsigned int i = 0; i < length; i++) {
    payload += (char)message[i];
  }

  Serial.print("Messaggio su [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(payload);

  // Parsa il JSON dello stato allarme
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.print("JSON non valido: ");
    Serial.println(err.c_str());
    return;
  }

  // "alarm": true  → allarme attivo  → accendi pin 4
  // "alarm": false → allarme reset   → spegni pin 4
  bool alarmActive = doc["alarm"] | false;
  digitalWrite(ALARM_PIN, alarmActive ? HIGH : LOW);
  Serial.print("Pin 4: ");
  Serial.println(alarmActive ? "ON (allarme attivo)" : "OFF");
}

void setup() {
  Serial.begin(115200);
  pinMode(ALARM_PIN, OUTPUT);
  digitalWrite(ALARM_PIN, LOW);
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void setup_wifi() {
  delay(10);
  // We start by connecting to a WiFi network
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Attempt to connect
    if (client.connect("ESP32AlarmSiren")) {
      Serial.println("connected");
      // Subscribe allo stato dell'allarme
      client.subscribe(ALARM_TOPIC);
      Serial.println("Sottoscritto a " ALARM_TOPIC);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

}
