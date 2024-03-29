#!/usr/bin/env python

"""
Creates a Client on the MQTT Protocol to communicate with Master

Client generates information to be sent to the Master when it's to be requested.
The communication is done through the MQTT Protocol with InfluxDB.
"""

# ------------------------------------------------------------------------------

# Standard Library
import random
import time
import sys
import threading

# 3rd Party Packages
import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import pandas as pd

# Local Source
from utils import *

__author__ = "António Pereira"
__email__ = "antonio_m_sp@hotmail.com"
__status__ = "Development"

# ------------------------------------------------------------------------------

def mathematical_calculation():
    """
    Calculation of PI using Leibniz's formula

    Objective of this function is to aid in adding cost to the generate data thread used by Client.
    """
    denominator = 1
    pi = 0

    for i in range(1000000):
        if i % 2 == 0:
            pi += 4 / denominator
        else:
            pi -= 4 / denominator

        denominator += 2
    return pi


def save_thread_timestamp_intervals_csv():
    """
    Writes the saved elapsed timestamp from generating_data() thread to clientID.csv
    """

    tmp_dict = {'Thread_Iteration': GEN_THREAD_ITERATION_DATA,
                'Time_Elapsed': GEN_THREAD_TIME_DATA,
                'MASTER_REQUEST': GEN_THREAD_REQUEST}

    df = pd.DataFrame(tmp_dict)
    sum_timestamps = sum(GEN_THREAD_TIME_DATA) * pow(10, -9)
    logging.info(CLIENT_ID + " - Solution time adding all time_elapsed of thread: {%.5f} seconds", sum_timestamps)
    timestr = time.strftime("%Y%m%d-%H%M%S")
    df.to_csv(SOLUTION_PATH + '\\' + CLIENT_ID + '_thread_time_elapsed_' + timestr + '.csv', index=False)


def welding_data_generation_simulation():
    """
    Generates the welding values with its assigned timestamps to be inserted in the DB.
    """
    global WELDING_DATA, GEN_THREAD_TIME_DATA, GEN_THREAD_ITERATION_AUX, GEN_THREAD_REQUEST, THREAD_START_TIME, THREAD_END_TIME, GEN_AUXILIAR_LIST
    # thread_start_time = time.thread_time_ns()
    logging.debug("Welding Simulator Working...")
    measurement_name = "weldingEvents"
    mathematical_calculation()

    for i in range(NUMBER_GENERATED_POINTS_PER_CYCLE):
        welding_value = format(round(random.uniform(0, 30), 4))
        uniqueID = str(i+1)
        time_now_temp = time.time_ns()
        WELDING_DATA.append("{measurement},client={client},uniqueID={uniqueID} welding_value={welding_value} {timestamp}"
                            .format(measurement=measurement_name,
                                    client=CLIENT_ID,
                                    uniqueID=uniqueID,
                                    welding_value=welding_value,
                                    timestamp=time_now_temp))


def store_welding_generation_DB(new_counter):
    """
    Writes the generated information to the client's DB.
    """

    global WELDING_DATA
    logging.debug("Storing generated welding data to DB...")

    client_write_start_time = time.perf_counter()
    db.write_points(WELDING_DATA, database=CLIENT_DB_NAME, time_precision='n', batch_size=10000,
                    protocol="line")  # try batch_size=10000
    client_write_end_time = time.perf_counter()
    welding_write_time_to_DB = client_write_end_time - client_write_start_time

    logging.debug(CLIENT_ID + " stored the welding generated data in: %.5f seconds", welding_write_time_to_DB)
    WELDING_DATA.clear()


def welding_workflow():
    """
    Thread in charge of the generate data generation loop

    Runs the welding data generation function several times before writing the all the generated data through store welding generation thread.
    Loop of program ends when MAX_CYCLE_LIMIT is reached.

    """
    logging.debug("Starting Welding Workflow Cycle Thread...")

    global MACHINE_WORKFLOW_CYCLE, ITERATOR_GENERATE_DATA, THREAD_START_TIME, THREAD_END_TIME, WELDING_ITERATOR_WORKFLOW, GEN_THREAD_ITERATION_AUX, THREAD_DB_START_TIME, THREAD_DB_END_TIME, FIRST_ITERATION_WORKFLOW

    new_counter = 0
    while MACHINE_WORKFLOW_CYCLE:
        generate_data_thread = threading.Thread(target=welding_data_generation_simulation, args=(), daemon=True)

        THREAD_START_TIME = time.perf_counter_ns()
        generate_data_thread.start()
        generate_data_thread.join()
        THREAD_END_TIME = time.perf_counter_ns()
        GEN_AUXILIAR_LIST.append(THREAD_END_TIME - THREAD_START_TIME)

        ITERATOR_GENERATE_DATA += 1

        if ITERATOR_GENERATE_DATA >= NUMBER_ITERATIONS_TILL_WRITE:
            new_counter += 1
            store_data_thread = threading.Thread(target=store_welding_generation_DB, args=(new_counter,), daemon=True)
            store_data_thread.start()
            store_data_thread.join()
            ITERATOR_GENERATE_DATA = 0

            GEN_THREAD_TIME_DATA.append(sum(GEN_AUXILIAR_LIST))  # thread_time
            GEN_THREAD_ITERATION_DATA.append(GEN_THREAD_ITERATION_AUX)  # thread_iterator number
            GEN_AUXILIAR_LIST.clear()

            if MASTER_REQ_INFO:
                GEN_THREAD_REQUEST.append("REQUEST")
            else:
                GEN_THREAD_REQUEST.append("IDLE")

        if WELDING_ITERATOR_WORKFLOW >= MAX_CYCLE_LIMIT-1:
            MACHINE_WORKFLOW_CYCLE = False

        GEN_THREAD_ITERATION_AUX += 1
        WELDING_ITERATOR_WORKFLOW += 1


def check_duplicate_timestamp_unused():
    """
    Checks if client's DB has any duplicate timestamp value
    """

    data = db.query("SELECT * FROM weldingEvents;")
    # print('Data raw: ', data.raw)
    points = data.get_points(tags={'client': CLIENT_ID})
    timestamp_list = []
    for point in points:
        # print("Time: {}, Welding value: {}".format(point['time'], point['welding_value']))
        timestamp_list.append(point['time'])


def send_client_data_to_master():
    """
    Send Client's DB data to Master's DB through influxDB
    """
    logging.debug("Sending all data in %s to master_db", CLIENT_DB_NAME)
    global MASTER_REQ_INFO, CLIENT_SENT_ALL_DATA
    db.switch_database(CLIENT_DB_NAME)

    client_write_start_time = time.perf_counter()
    send_data = db.query('SELECT * INTO master_db..weldingEvents FROM weldingEvents GROUP BY *;')
    client_write_end_time = time.perf_counter()

    client_write_time_to_master = client_write_end_time - client_write_start_time
    logging.info(CLIENT_ID + " sent Data to Master in: {%.5f} seconds\n", client_write_time_to_master)

    # logging.info("Query Successful: ", str(send_data))

    mqtt_client.publish(CLIENT_TOPIC, "ALL_INFORMATION_SENT", qos=1, retain=False)

    CLIENT_SENT_ALL_DATA = True
    MASTER_REQ_INFO = False


def clear_clientDB_data():
    """
    Clears every value from client's DB.
    """

    db.switch_database(CLIENT_DB_NAME)
    # db.drop_database(CLIENT_DB_NAME)

    query = "DROP SERIES FROM weldingEvents WHERE client=$client;"
    bind_params = {'client': CLIENT_ID}
    # logging.info("Starting to clean client DB..")
    deleted_data = db.query(query, bind_params=bind_params)
    # logging.info("Deleted data query: ", deleted_data)
    # logging.info("Deleted client DB..")


def influxDB_terminate():
    """
    Exit functions relative to influx database
    """
    db.close()


def init_logging_config():
    """
    Creates the logging file for the current clientID file in logs folder
    """

    logging.root.handlers = []

    if 'DEBUG_MODE' in sys.argv:
        logging.basicConfig(filename=SOLUTION_PATH + '\\' + CLIENT_ID + '.log', format='%(asctime)s : %(levelname)s : %(message)s',
                            level=logging.DEBUG, filemode='a')
    else:
        logging.basicConfig(filename=SOLUTION_PATH + '\\' + CLIENT_ID + '.log', format='%(asctime)s : %(levelname)s : %(message)s',
                            level=logging.INFO, filemode='a')

    # set up logging to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter('%(asctime)s : ' + SOLUTION_PATH + ' : %(levelname)s : %(message)s')
    console.setFormatter(formatter)
    logging.getLogger("").addHandler(console)


# MQTT Protocols


def on_connect(client, userdata, message, return_code):
    """
    MQTT connect protocol

    @param client:
        the client instance for this callback
    @param userdata:
        the private user data as set in Client() or userdata_set()
    @param message:
        response message sent by the broker
    @param return_code:
        the connection result\n
        0: Connection successful\n
        1: Connection refused – incorrect protocol version\n
        2: Connection refused – invalid client identifier\n
        3: Connection refused – server unavailable\n
        4: Connection refused – bad username or password\n
        5: Connection refused – not authorised\n
        6-255: Currently unused.\n
    """

    if return_code != 0:
        logging.info(CLIENT_ID + " - Error Connecting, Error Code: ", return_code)
        client.reconnect()
    else:
        logging.info(CLIENT_ID + " - Successfully Connected to Broker.\n")
        client.subscribe("topic/simulation/clients/#")  # subscribes to every topic of clients including itself
        client.subscribe("topic/simulation/master", qos=1)


def on_disconnect(client, userdata, rc):
    """
    Logs if any disconnect happened during execution of the program
    """
    logging.info("%s is disconnecting with reason: %s ", CLIENT_ID, str(rc))


def on_message(client, userdata, message):
    """
    Receives the messages that are published through the broker
    """

    if message.topic == "topic/simulation/master":
        decoded_message = str(message.payload.decode("utf-8"))
        global MACHINE_WORKFLOW_CYCLE, MASTER_REQ_INFO

        if decoded_message == "GET_INFORMATION":
            mqtt_protocol_print(message)
            MASTER_REQ_INFO = True

        elif decoded_message == "DATA_RECEIVED_FROM_" + CLIENT_ID:
            mqtt_protocol_print(message)
            pass

        elif decoded_message == "REQUEST_FINISHED":
            mqtt_protocol_print(message)
            # MACHINE_WORKFLOW_CYCLE = False


def mqtt_init(client):
    """
    Connects to Broker and initializes protocols
    """

    # broker_address = "broker.hivemq.com"
    broker_address = "localhost"
    broker_port = 1883

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(broker_address, port=broker_port)
    except ConnectionError:
        logging.info("Error connecting to Broker: %s, on Port: %s" % (broker_address, broker_port))
        client.reconnect()


def mqtt_terminate(client):
    """
    Calls the terminated functions of Client related to MQTT protocol
    """
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":

    # Arguments
    MACHINE_NUMBER = sys.argv[1]
    NUMBER_ITERATIONS_TILL_WRITE = int(sys.argv[2])
    NUMBER_GENERATED_POINTS_PER_CYCLE = int(sys.argv[3])
    SOLUTION_PATH = sys.argv[4]
    MAX_CYCLE_LIMIT = 250

    # Const Global Variables
    CLIENT_DB_NAME = 'client' + MACHINE_NUMBER + '_db'
    CLIENT_ID = 'client' + MACHINE_NUMBER
    CLIENT_TOPIC = "topic/simulation/clients/" + CLIENT_ID

    # Boolean Global Variables
    MACHINE_WORKFLOW_CYCLE = True
    CLIENT_SENT_ALL_DATA = False
    MASTER_REQ_INFO = False

    # Global Variables
    ITERATOR_GENERATE_DATA = 0
    WELDING_ITERATOR_WORKFLOW = 0
    THREAD_START_TIME = None
    THREAD_END_TIME = None
    THREAD_DB_START_TIME = None
    THREAD_DB_END_TIME = None
    WELDING_DATA = []
    FIRST_ITERATION_WORKFLOW = True

    GEN_THREAD_TIME_DATA = []  # time taken by thread
    GEN_THREAD_ITERATION_DATA = []  # thread iterator
    GEN_THREAD_REQUEST = []  # IDLE / REQUEST
    GEN_AUXILIAR_LIST = []

    GEN_THREAD_ITERATION_AUX = 1

    # ------------------------------------

    # Logging Configuration
    init_logging_config()

    # InfluxDB
    db = InfluxDBClient('localhost', 8086, 'root', 'root', CLIENT_DB_NAME)
    db.create_database(CLIENT_DB_NAME)

    # MQTT Protocol
    mqtt_client = mqtt.Client()
    mqtt_init(mqtt_client)

    welding_workflow_thread = threading.Thread(target=welding_workflow, args=(), daemon=True)
    welding_workflow_thread.start()

    mqtt_client.loop_start()

    mqtt_client.publish(CLIENT_TOPIC, "WORKING", qos=0, retain=True)

    while not MASTER_REQ_INFO:
        pass

    mqtt_client.publish(CLIENT_TOPIC, "SENDING_DATA", qos=0, retain=False)

    send_data_thread = threading.Thread(target=send_client_data_to_master, args=(), daemon=True)
    send_data_thread.start()

    while not CLIENT_SENT_ALL_DATA:
        pass

    while MACHINE_WORKFLOW_CYCLE:
        pass

    # Exit functions
    save_thread_timestamp_intervals_csv()
    influxDB_terminate()
    mqtt_terminate(mqtt_client)
