import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN

DEFAULT_CITY_ID = 19989
DEFAULT_SCAN_INTERVAL = 30

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Setup the sensor platform."""
    city_id = config.get("city_id", DEFAULT_CITY_ID)
    scan_interval_minutes = config.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    if isinstance(scan_interval_minutes, timedelta):
        scan_interval_minutes = int(scan_interval_minutes.total_seconds() / 60)
    elif not isinstance(scan_interval_minutes, int):
        raise TypeError("scan_interval must be an integer representing minutes")


    scan_interval = timedelta(minutes=scan_interval_minutes)
    sensors = []

    data = fetch_sungraph_data(city_id)

    if data:
        for entry in data:
            hour = entry["date"].split(' ')[1].replace(':', '_')
            sunshine_duration = round(entry["sunshineduration"])
            sensor_id = f"sat24_{hour}"
            sensor = SunGraphSensor(sensor_id, sunshine_duration, "%", "mdi:weather-sunny", hass)
            sensors.append(sensor)

        current_time = datetime.now().strftime('%H:00:00').replace(':', '_')
        current_entry = next((entry for entry in data if entry["date"].endswith(current_time.replace('_', ':'))), None)
        if current_entry:
            current_sunshine_duration = round(current_entry["sunshineduration"])
        else:
            current_sunshine_duration = 0

        current_sensor = SunGraphSensor("sat24_current", current_sunshine_duration, "%", "mdi:weather-sunny", hass)
        sensors.append(current_sensor)

        next_time = (datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).strftime('%H:%M:%S').replace(':', '_')
        next_entry = next((entry for entry in data if entry["date"].endswith(next_time.replace('_', ':'))), None)
        if next_entry:
            next_sunshine_duration = round(next_entry["sunshineduration"])
        else:
            next_sunshine_duration = 0

        next_sensor = SunGraphSensor("sat24_next", next_sunshine_duration, "%", "mdi:weather-sunny", hass)
        sensors.append(next_sensor)

    add_entities(sensors, True)

    async_track_time_interval(hass, lambda now: update_sensors(hass, city_id, sensors), scan_interval)

def fetch_sungraph_data(city_id):
    """Fetch the sun graph data from SAT24."""
    url = f"https://www.sat24.com/pl-pl/city/{city_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script')
        pattern = re.compile(r'SunGraph\.create\(\{.*?data:\s*(\[\{.*?\}\]),', re.DOTALL)

        for script in scripts:
            script_content = script.string
            if script_content:
                match = pattern.search(script_content)
                if match:
                    data_json = match.group(1)
                    data = json.loads(data_json)

                    for entry in data:
                        timestamp = entry["timestamp"]
                        date_str = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        entry["date"] = date_str

                    return data
    return None

def update_sensors(hass, city_id, sensors):
    """Update sensors with the latest data."""
    data = fetch_sungraph_data(city_id)
    if data:
        for sensor in sensors:
            for entry in data:
                if sensor.name.endswith(entry["date"].split(' ')[1].replace(':', '_')) or sensor.name in ["sat24_current", "sat24_next"]:
                    sunshine_duration = round(entry["sunshineduration"])
                    sensor.set_state(sunshine_duration)
                    break

class SunGraphSensor(SensorEntity):
    """Representation of a SunGraph Sensor."""

    def __init__(self, entity_id, sunshineduration, unit_of_measurement, icon, hass):
        """Initialize the sensor."""
        self.entity_id = f"sensor.{entity_id}"
        self._state = sunshineduration
        self._name = entity_id
        self._unit_of_measurement = unit_of_measurement
        self._icon = icon
        self.hass = hass

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    def set_state(self, sunshineduration):
        """Set the state of the sensor."""
        self._state = sunshineduration
        self.hass.add_job(self.async_schedule_update_ha_state)
