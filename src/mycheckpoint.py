#!/usr/bin/python

#
# Collect GLOBAL STATUS, GLOBAL VARIABLES, master & slave status, store in database, generate supporting views
#
# Released under the BSD license
#
# Copyright (c) 2009, Shlomi Noach
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#     * Neither the name of the organization nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import getpass
import MySQLdb
import traceback
import sys
from optparse import OptionParser


def parse_options():
    usage = "usage: mycheckpoint [options] [create/upgrade]"
    parser = OptionParser(usage=usage)
    parser.add_option("-u", "--user", dest="user", default="", help="MySQL user")
    parser.add_option("-H", "--host", dest="host", default="localhost", help="MySQL host (default: localhost)")
    parser.add_option("-p", "--password", dest="password", default="", help="MySQL password")
    parser.add_option("--ask-pass", action="store_true", dest="prompt_password", help="Prompt for password")
    parser.add_option("-P", "--port", dest="port", type="int", default="3306", help="TCP/IP port (default: 3306)")
    parser.add_option("-S", "--socket", dest="socket", default="/var/run/mysqld/mysql.sock", help="MySQL socket file. Only applies when host is localhost")
    parser.add_option("", "--defaults-file", dest="defaults_file", default="", help="Read from MySQL configuration file. Overrides all other options")
    parser.add_option("-d", "--database", dest="database", default="openark", help="Database name (required unless query uses fully qualified table names)")
    parser.add_option("", "--purge-days", dest="purge_days", type="int", default=182, help="Purge data older than specified amount of days (default: 182)")
    parser.add_option("", "--skip-disable-bin-log", dest="skip_disable_bin_log", action="store_true", default=False, help="Skip disabling the binary logging (binary loggind disabled by default)")
    parser.add_option("", "--skip-check-replication", dest="skip_check_replication", action="store_true", default=False, help="Skip checking on master/slave status variables")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="Print user friendly messages")
    parser.add_option("", "--chart-width", dest="chart_width", type="int", default=400, help="Google chart image width (default: 400)")
    parser.add_option("", "--chart-height", dest="chart_height", type="int", default=200, help="Google chart image height (default: 200)")
    return parser.parse_args()


def verbose(message):
    if options.verbose:
        print "-- %s" % message

def print_error(message):
    print "-- ERROR: %s" % message

def open_connection():
    if options.defaults_file:
        conn = MySQLdb.connect(
            read_default_file = options.defaults_file,
            db = database_name)
    else:
        if options.prompt_password:
            password=getpass.getpass()
        else:
            password=options.password
        conn = MySQLdb.connect(
            host = options.host,
            user = options.user,
            passwd = password,
            port = options.port,
            db = database_name,
            unix_socket = options.socket)
    return conn;

def act_query(query):
    """
    Run the given query, commit changes
    """
    connection = conn
    cursor = connection.cursor()
    num_affected_rows = cursor.execute(query)
    cursor.close()
    connection.commit()
    return num_affected_rows


def get_row(query):
    connection = conn
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query)
    row = cursor.fetchone()

    cursor.close()
    return row


def get_rows(query):
    connection = conn
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query)
    rows = cursor.fetchall()

    cursor.close()
    return rows


def table_exists(check_database_name, check_table_name):
    """
    See if the a given table exists:
    """
    count = 0

    query = """
        SELECT COUNT(*) AS count
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA='%s'
            AND TABLE_NAME='%s'
        """ % (check_database_name, check_table_name)

    row = get_row(query)
    count = int(row['count'])

    return count


def prompt_instructions():
    print "-- Creating mycheckpoint tables & views. Database name is `%s`" % database_name
    print "-- Make sure the user has ALL PRIVILEGES on the `%s` schema" % database_name
    print "-- e.g. GRANT ALL ON `%s`.* TO 'my_user'@'my_host' IDENTIFIED BY 'my_password'" % database_name
    print "-- The user will have to have the SUPER privilege in order to disable binary logging"
    print "-- + Otherwise, use --skip-disable-bin-log (but then be aware that slaves replicate this server's status)"
    print "-- In order to read master and slave status, the user must also be granted with REPLICATION CLIENT or SUPER privileges"
    print "-- + Otherwise, use --skip-check-replication"


def is_neglectable_variable(variable_name):
    if variable_name.startswith("ssl_"):
        return True
    if variable_name.startswith("ndb_"):
        return True
    if variable_name == "last_query_cost":
        return True
    return False


def normalize_variable_value(variable_value):
    if variable_value == "off":
        variable_value = 0
    elif variable_value == "on":
        variable_value = 1
    elif variable_value == "demand":
        variable_value = 2
    elif variable_value == "no":
        variable_value = 0
    elif variable_value == "yes":
        variable_value = 1
    return variable_value


def get_global_variables():
    global_variables = [
        "auto_increment_increment",
        "binlog_cache_size",
        "bulk_insert_buffer_size",
        "concurrent_insert",
        "connect_timeout",
        "delay_key_write",
        "delayed_insert_limit",
        "delayed_insert_timeout",
        "delayed_queue_size",
        "expire_logs_days",
        "foreign_key_checks",
        "group_concat_max_len",
        "innodb_additional_mem_pool_size",
        "innodb_autoextend_increment",
        "innodb_autoinc_lock_mode",
        "innodb_buffer_pool_size",
        "innodb_checksums",
        "innodb_commit_concurrency",
        "innodb_concurrency_tickets",
        "innodb_fast_shutdown",
        "innodb_file_io_threads",
        "innodb_file_per_table",
        "innodb_flush_log_at_trx_commit",
        "innodb_force_recovery",
        "innodb_lock_wait_timeout",
        "innodb_log_buffer_size",
        "innodb_log_file_size",
        "innodb_log_files_in_group",
        "innodb_max_dirty_pages_pct",
        "innodb_max_purge_lag",
        "innodb_mirrored_log_groups",
        "innodb_open_files",
        "innodb_rollback_on_timeout",
        "innodb_stats_on_metadata",
        "innodb_support_xa",
        "innodb_sync_spin_loops",
        "innodb_table_locks",
        "innodb_thread_concurrency",
        "innodb_thread_sleep_delay",
        "join_buffer_size",
        "key_buffer_size",
        "key_cache_age_threshold",
        "key_cache_block_size",
        "key_cache_division_limit",
        "large_files_support",
        "large_page_size",
        "large_pages",
        "locked_in_memory",
        "log_queries_not_using_indexes",
        "log_slow_queries",
        "long_query_time",
        "low_priority_updates",
        "max_allowed_packet",
        "max_binlog_cache_size",
        "max_binlog_size",
        "max_connect_errors",
        "max_connections",
        "max_delayed_threads",
        "max_error_count",
        "max_heap_table_size",
        "max_insert_delayed_threads",
        "max_join_size",
        "max_length_for_sort_data",
        "max_prepared_stmt_count",
        "max_relay_log_size",
        "max_seeks_for_key",
        "max_sort_length",
        "max_sp_recursion_depth",
        "max_tmp_tables",
        "max_user_connections",
        "max_write_lock_count",
        "min_examined_row_limit",
        "multi_range_count",
        "myisam_data_pointer_size",
        "myisam_max_sort_file_size",
        "myisam_repair_threads",
        "myisam_sort_buffer_size",
        "myisam_use_mmap",
        "net_buffer_length",
        "net_read_timeout",
        "net_retry_count",
        "net_write_timeout",
        "old_passwords",
        "open_files_limit",
        "optimizer_prune_level",
        "optimizer_search_depth",
        "port",
        "preload_buffer_size",
        "profiling",
        "profiling_history_size",
        "protocol_version",
        "pseudo_thread_id",
        "query_alloc_block_size",
        "query_cache_limit",
        "query_cache_min_res_unit",
        "query_cache_size",
        "query_cache_type",
        "query_cache_wlock_invalidate",
        "query_prealloc_size",
        "range_alloc_block_size",
        "read_buffer_size",
        "read_only",
        "read_rnd_buffer_size",
        "relay_log_space_limit",
        "rpl_recovery_rank",
        "server_id",
        "skip_external_locking",
        "skip_networking",
        "skip_show_database",
        "slave_compressed_protocol",
        "slave_net_timeout",
        "slave_transaction_retries",
        "slow_launch_time",
        "slow_query_log",
        "sort_buffer_size",
        "sql_auto_is_null",
        "sql_big_selects",
        "sql_big_tables",
        "sql_buffer_result",
        "sql_log_bin",
        "sql_log_off",
        "sql_log_update",
        "sql_low_priority_updates",
        "sql_max_join_size",
        "sql_notes",
        "sql_quote_show_create",
        "sql_safe_updates",
        "sql_select_limit",
        "sql_warnings",
        "sync_binlog",
        "sync_frm",
        "table_cache",
        "table_definition_cache",
        "table_lock_wait_timeout",
        "table_open_cache",
        "thread_cache_size",
        "thread_stack",
        "timed_mutexes",
        "timestamp",
        "tmp_table_size",
        "transaction_alloc_block_size",
        "transaction_prealloc_size",
        "unique_checks",
        "updatable_views_with_limit",
        "wait_timeout",
        "warning_count",
        ]
    return global_variables


def fetch_status_variables():
    """
    Fill in the status_dict. We make point of filling in all variables, even those not existing,
    for havign the dictionary hold the keys. Based on these keys, tables and views are created.
    So it is important that we have the dictionary include all possible keys.
    """
    if status_dict:
        return status_dict

    query = "SHOW GLOBAL STATUS"
    rows = get_rows(query);
    for row in rows:
        variable_name = row["Variable_name"].lower()
        variable_value = row["Value"].lower()
        if not is_neglectable_variable(variable_name):
            status_dict[variable_name] = normalize_variable_value(variable_value)

    # Listing of interesting global variables:
    global_variables = get_global_variables()
    for variable_name in global_variables:
        status_dict[variable_name.lower()] = None
    query = "SHOW GLOBAL VARIABLES"
    rows = get_rows(query);
    for row in rows:
        variable_name = row["Variable_name"].lower()
        variable_value = row["Value"].lower()
        if variable_name in global_variables:
            status_dict[variable_name] = normalize_variable_value(variable_value)

    # Master & slave status
    status_dict["master_status_position"] = None
    status_dict["master_status_file_number"] = None
    slave_status_variables = [
        "Read_Master_Log_Pos",
        "Relay_Log_Pos",
        "Exec_Master_Log_Pos",
        "Relay_Log_Space",
        "Seconds_Behind_Master",
        ]
    for variable_name in slave_status_variables:
        status_dict[variable_name.lower()] = None
    if not options.skip_check_replication:
        try:
            query = "SHOW MASTER STATUS"
            master_status = get_row(query)
            if master_status:
                status_dict["master_status_position"] = master_status["Position"]
                log_file_name = master_status["File"]
                log_file_number = int(log_file_name.rsplit(".")[-1])
                status_dict["master_status_file_number"] = log_file_number
            query = "SHOW SLAVE STATUS"
            slave_status = get_row(query)
            if slave_status:
                for variable_name in slave_status_variables:
                    status_dict[variable_name.lower()] = slave_status[variable_name]
        except:
            # An exception can be thrown if the user does not have enough privileges:
            verbose("Cannot show master & slave status. Skipping")
            pass

    return status_dict


def get_status_variables_columns():
    """
    Return all columns participating in the status variables table. Most of these are STATUS variables.
    Others are parameters. Others yet represent slave or master status etc.
    """
    status_dict = fetch_status_variables()
    return sorted(status_dict.keys())


def get_variables_and_status_columns():
    variables_columns = get_global_variables()
    status_columns = [column_name for column_name in get_status_variables_columns() if not column_name in variables_columns]
    return variables_columns, status_columns


def get_column_sign_indicator(column_name):
    known_signed_diff_status_variables = [
        "threads_cached",
        "threads_connected",
        "threads_running",
        "open_table_definitions",
        "open_tables",
        "slave_open_temp_tables",
        "qcache_free_blocks",
        "qcache_free_memory",
        "qcache_queries_in_cache",
        "qcache_total_blocks",
        "innodb_page_size",
        "innodb_buffer_pool_pages_total",
        "innodb_buffer_pool_pages_free",
        "key_blocks_unused",
        "key_cache_block_size",
        "master_status_position",
        "Read_Master_Log_Pos",
        "Relay_Log_Pos",
        "Exec_Master_Log_Pos",
        "Relay_Log_Space",
        "Seconds_Behind_Master",
        ]
    if column_name in known_signed_diff_status_variables:
        return "SIGNED"
    else:
        return "UNSIGNED"


def create_status_variables_table():
    columns_listing = ",\n".join(["%s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in get_status_variables_columns()])
    query = """CREATE TABLE %s.%s (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            %s,
            UNIQUE KEY ts (ts)
       )
        """ % (database_name, table_name, columns_listing)
    act_query(query)


def create_numbers_table():
    query = """CREATE TABLE IF NOT EXISTS %s.numbers (
                n SMALLINT UNSIGNED NOT NULL,
                PRIMARY KEY (n)
            )
        """ % database_name
    act_query(query)
    numbers_values = ",".join(["(%d)" % n for n in range(0,4096)])
    query = """
        INSERT IGNORE INTO %s.numbers
        VALUES %s
        """ % (database_name, numbers_values)
    act_query(query)


def upgrade_status_variables_table():
    query = """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='%s' AND TABLE_NAME='%s'
        """ % (database_name, table_name)
    existing_columns = [row["COLUMN_NAME"] for row in get_rows(query)]
    new_columns = [column_name for column_name in get_status_variables_columns() if column_name not in existing_columns]

    if new_columns:
        columns_listing = ",\n".join(["ADD COLUMN %s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in new_columns])
        query = """ALTER TABLE %s.%s
                %s
        """ % (database_name, table_name, columns_listing)
        act_query(query)
    verbose("status_variables table upgraded")


def create_status_variables_diff_view():
    global_variables, status_columns = get_variables_and_status_columns()
    # Global variables are used as-is
    global_variables_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s AS %s" % (column_name, column_name,) for column_name in global_variables])
    # status variables as they were:
    status_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s AS %s" % (column_name, column_name,) for column_name in status_columns])
    # Status variables are diffed. This does not make sense for all of them, but we do it for all nonetheless.
    diff_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s - ${status_variables_table_alias}1.%s AS %s_diff" % (column_name, column_name, column_name,) for column_name in status_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_diff AS
          SELECT
            ${status_variables_table_name}2.id,
            ${status_variables_table_name}2.ts,
            TIMESTAMPDIFF(SECOND, ${status_variables_table_name}1.ts, ${status_variables_table_name}2.ts) AS ts_diff_seconds,
            %s,
            %s,
            %s
          FROM
            ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}1
            INNER JOIN ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}2
            ON (${status_variables_table_alias}1.id = ${status_variables_table_alias}2.id-GREATEST(1, IFNULL(${status_variables_table_alias}2.auto_increment_increment, 1)))
    """ % (status_columns_listing, diff_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${status_variables_table_name}", table_name)
    query = query.replace("${status_variables_table_alias}", table_name)
    act_query(query)

    verbose("sv_diff view created")


def create_status_variables_sample_view():
    global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join(["%s" % (column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" %s" % (column_name,) for column_name in status_columns])
    diff_columns_listing = ",\n".join([" %s_diff" % (column_name,) for column_name in status_columns])
    change_psec_columns_listing = ",\n".join([" ROUND(%s_diff/ts_diff_seconds, 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_sample AS
          SELECT
            id,
            ts,
            ts_diff_seconds,
            %s,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_diff
        """ % (status_columns_listing, diff_columns_listing, change_psec_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_sample view created")


def create_status_variables_hour_view():
    global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" %s" % (column_name,) for column_name in status_columns])
    sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
    avg_psec_columns_listing = ",\n".join([" ROUND(AVG(%s_psec), 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_hour AS
          SELECT
            MIN(id) AS id,
            DATE(ts) + INTERVAL HOUR(ts) HOUR AS ts,
            DATE(ts) + INTERVAL (HOUR(ts) + 1) HOUR AS end_ts,
            SUM(ts_diff_seconds) AS ts_diff_seconds,
            %s,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_sample
          GROUP BY DATE(ts), HOUR(ts)
    """ % (status_columns_listing, sum_diff_columns_listing, avg_psec_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_hour view created")


def create_status_variables_day_view():
    global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join([" MIN(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" %s" % (column_name,) for column_name in status_columns])
    sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
    avg_psec_columns_listing = ",\n".join([" ROUND(AVG(%s_psec), 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_day AS
          SELECT
            MIN(id) AS id,
            DATE(ts) AS ts,
            DATE(ts) + INTERVAL 1 DAY AS end_ts,
            SUM(ts_diff_seconds) AS ts_diff_seconds,
            %s,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_sample
          GROUP BY DATE(ts)
    """ % (status_columns_listing, sum_diff_columns_listing, avg_psec_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_day view created")


def create_report_recent_views():
    """
    Generate per-sample, per-hour and per-day 'recent' views, which only list the latest 256 rows from respective full views.
    """
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_report_${view_name_extension}_recent AS
          SELECT *
          FROM
            ${database_name}.sv_report_${view_name_extension}
          ORDER BY id DESC
          LIMIT 256
        """
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        custom_query = query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("recent reports views created")


def create_report_recent_minmax_views():
    """
    Generate min/max values view for the recent views.
    """
    global_variables, status_columns = get_variables_and_status_columns()

    #all_columns = []
    #all_columns.extend(["%s" % (column_name,) for column_name in status_columns])
    #all_columns.extend(["%s_diff" % (column_name,) for column_name in status_columns])
    #all_columns.extend(["%s_psec" % (column_name,) for column_name in status_columns])

    all_columns = custom_views_columns["report"]

    min_columns_listing = ",\n".join(["MIN(%s) AS %s_min" % (column_name, column_name,) for column_name in all_columns])
    max_columns_listing = ",\n".join(["MAX(%s) AS %s_max" % (column_name, column_name,) for column_name in all_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_report_${view_name_extension}_recent_minmax AS
          SELECT
            COUNT(*) AS count_rows,
            MIN(TS) AS ts_min,
            MAX(ts) AS ts_max,
            TIMESTAMPDIFF(SECOND, MIN(TS), MAX(ts)) AS ts_diff_seconds,

            %s,
            %s
          FROM
            ${database_name}.sv_report_${view_name_extension}_recent
          ORDER BY id DESC
          LIMIT 256
        """ % (min_columns_listing, max_columns_listing)
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        custom_query = query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("recent reports minmax views created")


def create_status_variables_parameter_change_view():
    global_variables, diff_columns = get_variables_and_status_columns()

    global_variables_select_listing = ["""
        SELECT ${status_variables_table_alias}2.ts AS ts, '%s' AS variable_name, ${status_variables_table_alias}1.%s AS old_value, ${status_variables_table_alias}2.%s AS new_value
        FROM
          ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}1
          INNER JOIN ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}2
          ON (${status_variables_table_alias}1.id = ${status_variables_table_alias}2.id-GREATEST(1, IFNULL(${status_variables_table_alias}2.auto_increment_increment, 1)))
        WHERE ${status_variables_table_alias}2.%s != ${status_variables_table_alias}1.%s
        """ % (column_name, column_name, column_name,
               column_name, column_name,) for column_name in global_variables if column_name != 'timestamp']
    global_variables_select_union = " UNION ALL \n".join(global_variables_select_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_parameter_change_union AS
          %s
    """ % (global_variables_select_union,)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${status_variables_table_name}", table_name)
    query = query.replace("${status_variables_table_alias}", table_name)
    act_query(query)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_param_change AS
          SELECT *
          FROM ${database_name}.sv_parameter_change_union
          ORDER BY ts, variable_name
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_param_change view created")


def create_status_variables_long_format_view():
    global_variables, status_variables = get_variables_and_status_columns()
    all_columns_listing = []
    all_columns_listing.extend(global_variables);
    all_columns_listing.extend(status_variables);
    all_columns_listing.extend(["%s_diff" % (column_name,) for column_name in status_variables])
    all_columns_listing.extend(["%s_psec" % (column_name,) for column_name in status_variables])
    all_columns = ",".join(all_columns_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_long_hour AS
            SELECT
                id, ts,
                SUBSTRING_INDEX(SUBSTRING_INDEX('%s', ',', numbers.n), ',', -1) AS variable_name,
                CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(CONCAT_WS(',', %s), ',', numbers.n), ',', -1) AS UNSIGNED) AS variable_value
            FROM
                ${database_name}.sv_hour,
                ${database_name}.numbers
            WHERE
                numbers.n >= 1 AND numbers.n <= %d
            ORDER BY
                id ASC, variable_name ASC
        """ % (all_columns, all_columns, len(all_columns_listing))
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_status_variables_aggregated_view():
    global_variables, status_variables = get_variables_and_status_columns()
    all_columns_listing = []
    all_columns_listing.extend(global_variables);
    all_columns_listing.extend(status_variables);
    all_columns = ",".join(all_columns_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_agg_hour AS
            SELECT
                MIN(id) AS id, MIN(ts) AS min_ts, MAX(ts) AS max_ts,
                SUBSTRING_INDEX(SUBSTRING_INDEX('%s', ',', numbers.n), ',', -1) AS variable_name,
                GROUP_CONCAT(CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(CONCAT_WS(',', %s), ',', numbers.n), ',', -1) AS UNSIGNED) ORDER BY ts ASC) AS variable_values
            FROM
                ${database_name}.sv_hour,
                ${database_name}.numbers
            WHERE
                numbers.n >= 1 AND numbers.n <= %d
            GROUP BY
                variable_name ASC
        """ % (all_columns, all_columns, len(all_columns_listing))
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_custom_views(view_base_name, view_columns, custom_columns = ""):
    global_variables, status_variables = get_variables_and_status_columns()

    view_columns_list = [column_name.strip() for column_name in view_columns.lower().split(",")]
    all_columns_listing = []
    all_columns_listing.extend([column_name for column_name in view_columns_list if column_name in global_variables])
    all_columns_listing.extend([column_name for column_name in view_columns_list if column_name in status_variables])
    all_columns_listing.extend([" %s_diff" % (column_name,) for column_name in view_columns_list if column_name in status_variables])
    all_columns_listing.extend(["%s_psec" % (column_name,) for column_name in view_columns_list if column_name in status_variables])
    columns_listing = ",\n".join(all_columns_listing)
    if custom_columns:
        if view_columns:
            columns_listing = columns_listing + ",\n "
        columns_listing = columns_listing + custom_columns

    # This is currently an ugly patch (first one in this code...)
    # We need to know which custom columns have been created in the "report" views, so that we can later build the
    # sv_report_minmax_* views.
    # So we parse the custom columns. We expect one column per line; we allow for aliasing (" as ")
    # We then store the columns for later use.
    custom_columns_names_list = [column_name for column_name in custom_columns.lower().split("\n")]
    custom_columns_names_list = [column_name.split(" as ")[-1].replace(",","").strip() for column_name in custom_columns_names_list]
    custom_columns_names_list = [column_name for column_name in custom_columns_names_list if column_name]
    custom_views_columns[view_base_name] = custom_columns_names_list

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_%s_${view_name_extension} AS
          SELECT
            id,
            ts,
            %s
          FROM
            ${database_name}.sv_${view_name_extension}
    """ % (view_base_name,
           columns_listing)
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        custom_query = query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("%s custom view created" % view_base_name)


def generate_google_chart_query(chart_columns, alias, ts_format, scale_from_0=False, scale_to_100=False):
    chart_columns_list = [column_name.strip() for column_name in chart_columns.lower().split(",")]

    chart_column_min_listing = ",".join(["%s_min" % column_name for column_name in chart_columns_list])
    chart_column_max_listing = ",".join(["%s_max" % column_name for column_name in chart_columns_list])

    if scale_from_0:
        least_value_clause = "LEAST(0,%s)" % chart_column_min_listing
    elif len(chart_columns_list) > 1:
        least_value_clause = "LEAST(%s)" % chart_column_min_listing
    else:
        # Sadly, LEAST doesn;t work for 1 argument only... So we need a special case here
        least_value_clause = chart_column_min_listing

    if scale_to_100:
        greatest_value_clause = "GREATEST(100,%s)" % chart_column_max_listing
    elif len(chart_columns_list) > 1:
        greatest_value_clause = "GREATEST(%s)" % chart_column_max_listing
    else:
        # Sadly, LEAST doesn;t work for 1 argument only... So we need a special case here
        greatest_value_clause = chart_column_max_listing


    piped_chart_column_listing = "|".join(chart_columns_list)

    chart_colors = ["ff8c00", "4682b4", "9acd32", "dc143c", "9932cc", "ffd700", "191970", "7fffd4", "808080", "dda0dd"][0:len(chart_columns_list)]

    column_values = [ """
            GROUP_CONCAT(SUBSTRING(
              'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
              ROUND(
                61 *
                (%s - ${least_value_clause})/(${greatest_value_clause} - ${least_value_clause})
              ), 1)
              ORDER BY ts ASC
              SEPARATOR ''
            ),
            """ % (column_name) for column_name in chart_columns_list
        ]
    concatenated_column_values = "',',".join(column_values)

    num_x_values = 5
    x_values = ",".join(["""'|', DATE_FORMAT(ts_min + INTERVAL (ts_diff_seconds*%d/%d) SECOND, '${ts_format}')""" % (i, num_x_values) for i in range(1,num_x_values)])

    query = """
          REPLACE(
          CONCAT(
            'http://chart.apis.google.com/chart?cht=lc&chs=${chart_width}x${chart_height}&chts=303030,12&chtt=',
            DATE_FORMAT(ts_min, '${ts_format}'), '  -  ', DATE_FORMAT(ts_max, '${ts_format}'),
              ' (', TIMESTAMPDIFF(DAY, MIN(ts), MAX(ts)), ' days, ',
              TIMESTAMPDIFF(HOUR, ts_min, ts_max) % 24, ' hours)',
            '&chdl=${piped_chart_column_listing}&chdlp=b&chco=${chart_colors}&chd=s:',
            ${concatenated_column_values}
            '&chxt=x,y&chxr=1,', ${least_value_clause},',', ${greatest_value_clause}, '&chxl=0:|', ${x_values}, '|&chxs=0,505050,10'
          ), ' ', '+') AS ${alias}
        """
    query = query.replace("${database_name}", database_name)
    query = query.replace("${chart_width}", str(options.chart_width))
    query = query.replace("${chart_height}", str(options.chart_height))
    query = query.replace("${piped_chart_column_listing}", piped_chart_column_listing)
    query = query.replace("${chart_colors}", ",".join(chart_colors))
    query = query.replace("${concatenated_column_values}", concatenated_column_values)
    query = query.replace("${least_value_clause}", least_value_clause)
    query = query.replace("${greatest_value_clause}", greatest_value_clause)
    query = query.replace("${alias}", alias)
    query = query.replace("${x_values}", x_values)
    query = query.replace("${ts_format}", ts_format)

    return query


def create_report_google_chart_view(charts_list):

    ts_formats_map = {
        "sample": "%b %e, %H:%i",
        "hour": "%b %e, %H:00",
        "day": "%b %e, %y",
        }

    for view_name_extension in ["sample", "hour", "day"]:
        ts_format = ts_formats_map[view_name_extension]
        charts_queries = [generate_google_chart_query(chart_columns, alias, ts_format, scale_from_0, scale_to_100) for (chart_columns, alias, scale_from_0, scale_to_100) in charts_list]
        charts_query = ",".join(charts_queries)
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY DEFINER
            VIEW ${database_name}.sv_report_chart_${view_name_extension} AS
              SELECT
                %s
              FROM
                ${database_name}.sv_report_${view_name_extension}_recent, ${database_name}.sv_report_${view_name_extension}_recent_minmax
            """ % charts_query
        query = query.replace("${database_name}", database_name)
        query = query.replace("${view_name_extension}", view_name_extension)
        act_query(query)

    verbose("report charts views created")


def create_report_html_view(charts_aliases):
    charts_aliases_list = [chart_alias.strip() for chart_alias in charts_aliases.split(",")]

    all_img_tags_queries = []
    for chart_alias in charts_aliases_list:
        alias_img_tags_query = """
            '<div class="row">
                <a name="${chart_alias}"></a>
                <h2>${chart_alias}</h2>',
                '<div class="chart">', IFNULL(CONCAT('<img src="', sv_report_chart_sample.${chart_alias}, '"/>'), 'N/A'), '</div>',
                '<div class="chart">', IFNULL(CONCAT('<img src="', sv_report_chart_hour.${chart_alias}, '"/>'), 'N/A'), '</div>',
                '<div class="chart">', IFNULL(CONCAT('<img src="', sv_report_chart_day.${chart_alias}, '"/>'), 'N/A'), '</div>',
                '<div class="clear"></div>',
            '</div>
                ',
            """
        alias_img_tags_query = alias_img_tags_query.replace("${chart_width}", str(options.chart_width))
        alias_img_tags_query = alias_img_tags_query.replace("${chart_height}", str(options.chart_height))
        alias_img_tags_query = alias_img_tags_query.replace("${chart_alias}", chart_alias)
        all_img_tags_queries.append(alias_img_tags_query)
    all_img_tags_query = "".join(all_img_tags_queries)

    chart_aliases_map = " | ".join(["""<a href="#%s">%s</a>""" % (chart_alias, chart_alias,) for chart_alias in charts_aliases_list])
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY DEFINER
        VIEW ${database_name}.sv_report_html AS
          SELECT CONCAT('
    <html>
        <head>
        <title>mycheckpoint report</title>
        <style type="text/css">
            body {
                background:#FFFFFF none repeat scroll 0% 0%;
                color:#505050;
                font-family:Verdana,Arial,Helvetica,sans-serif;
                font-size:9pt;
                line-height:1.5;
            }
            a {
                color:#f26522;
                text-decoration:none;
            }
            h2 {
                font-weight:normal;
                margin-top:20px;
            }
            .nobr {
                white-space: nowrap;
            }
            div.row {
                width: ${global_width};
            }
            div.chart {
                float: left;
                white-space: nowrap;
                margin-right: 10px;
                width: ${chart_width};
                height: ${chart_height};
            }
            div.chart img {
                border:0px none;
                width: ${chart_width};
                height: ${chart_height};
            }
            .clear {
                clear:both;
                height:1px;
            }
        </style>
        </head>
        <body>
            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on ', NOW(), '
            <br/><br/>
            Navigate: ${chart_aliases_map}
            <br/>
            ',
            %s '
        </body>
    </html>
          ') AS html
          FROM
            ${database_name}.sv_report_chart_sample, ${database_name}.sv_report_chart_hour, ${database_name}.sv_report_chart_day
        """ % all_img_tags_query
    query = query.replace("${database_name}", database_name)
    query = query.replace("${chart_aliases_map}", chart_aliases_map)
    query = query.replace("${global_width}", str(options.chart_width*3 + 30))
    query = query.replace("${chart_width}", str(options.chart_width))
    query = query.replace("${chart_height}", str(options.chart_height))
    act_query(query)

    verbose("report html view created")


def create_status_variables_views():
    global_variables, status_columns = get_variables_and_status_columns()
    create_status_variables_diff_view()
    create_status_variables_sample_view()
    create_status_variables_hour_view()
    create_status_variables_day_view()
    create_status_variables_parameter_change_view()
    #create_status_variables_long_format_view()
    #create_status_variables_aggregated_view()
    create_custom_views("dml", """
            concurrent_insert,
            com_select, com_insert, com_update, com_delete, com_replace,
            com_commit,
            questions, slow_queries
        """,
        """
            ROUND(100*com_select_diff/NULLIF(questions_diff, 0), 2) AS com_select_percent,
            ROUND(100*com_insert_diff/NULLIF(questions_diff, 0), 2) AS com_insert_percent,
            ROUND(100*com_update_diff/NULLIF(questions_diff, 0), 2) AS com_update_percent,
            ROUND(100*com_delete_diff/NULLIF(questions_diff, 0), 2) AS com_delete_percent,
            ROUND(100*com_replace_diff/NULLIF(questions_diff, 0), 2) AS com_replace_percent,
            ROUND(100*com_commit_diff/NULLIF(questions_diff, 0), 2) AS com_commit_percent,
            ROUND(100*slow_queries_diff/NULLIF(questions_diff, 0), 2) AS slow_queries_percent
        """)
    com_commands = [column_name for column_name in status_columns if column_name.startswith("com_")]
    create_custom_views("com", ",\n ".join(com_commands),
            ",\n ".join(
                ["ROUND(100*(%s)/NULLIF(questions_diff, 0), 2) AS %s_percent" % (column_name, column_name,) for column_name in com_commands])
            )

    create_custom_views("select", """
            com_select,
            select_scan, sort_merge_passes, sort_range, sort_rows, sort_scan
        """,
        """
            ROUND(100*select_scan_diff/NULLIF(com_select_diff, 0), 2) AS select_scan_percent,
            ROUND(100*select_full_join_diff/NULLIF(com_select_diff, 0), 2) AS select_full_join_percent,
            ROUND(100*select_range_diff/NULLIF(com_select_diff, 0), 2) AS select_range_percent
        """)
    create_custom_views("tmp_tables", """
            tmp_table_size, max_heap_table_size, created_tmp_tables, created_tmp_disk_tables
        """,
        """
            ROUND(100*created_tmp_disk_tables/NULLIF(created_tmp_tables, 0), 2) AS created_disk_tmp_tables_percent
        """)
    create_custom_views("threads", """
            max_delayed_threads, max_insert_delayed_threads, thread_cache_size, thread_stack,
            delayed_insert_threads, slow_launch_threads, threads_cached, threads_connected, threads_created, threads_running
        """)
    create_custom_views("connections", """
            max_connections,
            connections, aborted_connects
        """,
        """
            ROUND(100*aborted_connects_diff/NULLIF(connections_diff, 0), 2) AS aborted_connections_percent
        """)
    create_custom_views("table_cache", """
            table_cache, table_open_cache, table_definition_cache,
            open_tables, opened_tables
        """,
        """
            ROUND(100*open_tables/NULLIF(table_cache, 0), 2) AS table_cache_50_use_percent,
            ROUND(100*open_tables/NULLIF(table_open_cache, 0), 2) AS table_cache_51_use_percent
        """)
    create_custom_views("innodb_io", """
            innodb_buffer_pool_size, innodb_page_size,
            innodb_buffer_pool_write_requests, innodb_buffer_pool_pages_flushed,
            innodb_buffer_pool_read_requests, innodb_buffer_pool_reads,
            innodb_log_write_requests, innodb_log_writes,
            innodb_os_log_written,
            innodb_rows_read
        """,
        """
            ROUND(innodb_os_log_written_psec*60*60/1024/1024, 1) AS innodb_estimated_log_mb_written_per_hour,
            ROUND(100 - (100*innodb_buffer_pool_reads/NULLIF(innodb_buffer_pool_read_requests, 0)), 2) AS innodb_read_hit_percent,
            innodb_buffer_pool_pages_total * innodb_page_size AS innodb_buffer_pool_total_bytes,
            (innodb_buffer_pool_pages_total - innodb_buffer_pool_pages_free) * innodb_page_size AS innodb_buffer_pool_used_bytes,
            ROUND(100 - 100*innodb_buffer_pool_pages_free/NULLIF(innodb_buffer_pool_pages_total, 0), 2) AS innodb_buffer_pool_used_percent
        """)
    create_custom_views("innodb_io_summary", """
            innodb_buffer_pool_size,
            innodb_flush_log_at_trx_commit
        """,
        """
            ROUND(innodb_os_log_written_psec*60*60/1024/1024, 1) AS innodb_estimated_log_mb_written_per_hour,
            ROUND(100 - (100*innodb_buffer_pool_reads_diff/NULLIF(innodb_buffer_pool_read_requests_diff, 0)), 2) AS innodb_read_hit_percent,
            ROUND(100 - 100*innodb_buffer_pool_pages_free/NULLIF(innodb_buffer_pool_pages_total, 0), 2) AS innodb_buffer_pool_used_percent,
            innodb_buffer_pool_reads_psec,
            innodb_buffer_pool_pages_flushed_psec
        """)
    create_custom_views("myisam_io", """
            key_buffer_size,
            key_buffer_used,
            key_read_requests, key_reads,
            key_write_requests, key_writes,
        """,
        """
            key_buffer_size - (key_blocks_unused * key_cache_block_size) AS key_buffer_usage,
            ROUND(100 - 100*(key_blocks_unused * key_cache_block_size)/NULLIF(key_buffer_size, 0), 2) AS key_buffer_usage_percent,
            ROUND(100 - 100*key_reads_diff/NULLIF(key_read_requests_diff, 0), 2) AS key_read_hit_percent,
            ROUND(100 - 100*key_writes_diff/NULLIF(key_write_requests_diff, 0), 2) AS key_write_hit_percent
        """)
    create_custom_views("locks", """
            innodb_lock_wait_timeout,
            table_locks_waited, table_locks_immediate
        """,
        """
            ROUND(100*table_locks_waited_diff/NULLIF(table_locks_waited_diff + table_locks_immediate_diff, 0), 2) AS table_lock_waited_percent,
            innodb_row_lock_waits_psec, innodb_row_lock_current_waits
        """)
    create_custom_views("replication", """
            max_binlog_size, sync_binlog,
            max_relay_log_size, relay_log_space_limit,
            master_status_position,  master_status_file_number,
            Read_Master_Log_Pos, Relay_Log_Pos, Exec_Master_Log_Pos, Relay_Log_Space, Seconds_Behind_Master,
        """)
    create_custom_views("report", "", """
            ROUND(100*uptime_diff/NULLIF(ts_diff_seconds, 0), 1) AS uptime_percent,

            innodb_buffer_pool_size,
            innodb_flush_log_at_trx_commit,
            ROUND(100 - 100*innodb_buffer_pool_pages_free/NULLIF(innodb_buffer_pool_pages_total, 0), 1) AS innodb_buffer_pool_used_percent,
            ROUND(100 - (100*innodb_buffer_pool_reads_diff/NULLIF(innodb_buffer_pool_read_requests_diff, 0)), 2) AS innodb_read_hit_percent,
            innodb_buffer_pool_reads_psec,
            innodb_buffer_pool_pages_flushed_psec,
            innodb_os_log_written_psec,
            ROUND(innodb_os_log_written_psec*60*60/1024/1024, 1) AS innodb_estimated_log_mb_written_per_hour,
            innodb_row_lock_waits_psec,
            innodb_row_lock_current_waits,

            bytes_sent_psec/1024/1024 AS mega_bytes_sent_psec,
            bytes_received_psec/1024/1024 AS mega_bytes_received_psec,

            key_buffer_size,
            ROUND(100 - 100*(key_blocks_unused * key_cache_block_size)/NULLIF(key_buffer_size, 0), 1) AS key_buffer_used_percent,
            ROUND(100 - 100*key_reads_diff/NULLIF(key_read_requests_diff, 0), 1) AS key_read_hit_percent,
            ROUND(100 - 100*key_writes_diff/NULLIF(key_write_requests_diff, 0), 1) AS key_write_hit_percent,

            com_select_psec,
            com_insert_psec,
            com_update_psec,
            com_delete_psec,
            com_replace_psec,
            com_set_option_psec,
            com_commit_psec,
            slow_queries_psec,
            questions_psec,
            ROUND(100*com_select_diff/NULLIF(questions_diff, 0), 1) AS com_select_percent,
            ROUND(100*com_insert_diff/NULLIF(questions_diff, 0), 1) AS com_insert_percent,
            ROUND(100*com_update_diff/NULLIF(questions_diff, 0), 1) AS com_update_percent,
            ROUND(100*com_delete_diff/NULLIF(questions_diff, 0), 1) AS com_delete_percent,
            ROUND(100*com_replace_diff/NULLIF(questions_diff, 0), 1) AS com_replace_percent,
            ROUND(100*com_set_option_diff/NULLIF(questions_diff, 0), 1) AS com_set_option_percent,
            ROUND(100*com_commit_diff/NULLIF(questions_diff, 0), 1) AS com_commit_percent,
            ROUND(100*slow_queries_diff/NULLIF(questions_diff, 0), 1) AS slow_queries_percent,

            select_scan_psec,
            select_full_join_psec,
            select_range_psec,
            ROUND(100*select_scan_diff/NULLIF(com_select_diff, 0), 1) AS select_scan_percent,
            ROUND(100*select_full_join_diff/NULLIF(com_select_diff, 0), 1) AS select_full_join_percent,
            ROUND(100*select_range_diff/NULLIF(com_select_diff, 0), 1) AS select_range_percent,

            table_locks_waited_psec,
            ROUND(100*table_locks_waited_diff/NULLIF(table_locks_waited_diff + table_locks_immediate_diff, 0), 1) AS table_lock_waited_percent,

            IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0) AS table_cache_size,
            open_tables,
            ROUND(100*open_tables/NULLIF(IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0), 0), 1) AS table_cache_use_percent,
            opened_tables_psec,

            created_tmp_tables_psec,
            created_tmp_disk_tables_psec,
            ROUND(100*created_tmp_disk_tables_diff/NULLIF(created_tmp_tables_diff, 0), 1) AS created_disk_tmp_tables_percent,

            max_connections,
            ROUND(100*max_used_connections/NULLIF(max_connections, 0), 1) AS max_connections_used_percent,
            connections_psec,
            aborted_connects_psec,
            ROUND(100*aborted_connects_diff/NULLIF(connections_diff, 0), 1) AS aborted_connections_percent,

            thread_cache_size,
            ROUND(100*threads_cached/NULLIF(thread_cache_size, 0), 1) AS thread_cache_used_percent,
            threads_created_psec,
            threads_connected,
            ROUND(100*threads_connected/NULLIF(max_connections, 0), 1) AS threads_connected_used_percent,

            master_status_file_number,
            master_status_position,
            max_relay_log_size,
            relay_log_space,
            ROUND(100 - 100*relay_log_space/NULLIF(max_relay_log_size, 0), 1) AS relay_log_space_used_percent,
            seconds_behind_master
        """)
    create_report_recent_views()
    create_report_recent_minmax_views()
    create_custom_views("report_human", "", """CONCAT('
    Report period: ', TIMESTAMP(ts), ' to ', TIMESTAMP(ts) + INTERVAL ROUND(ts_diff_seconds/60) MINUTE, '. Period is ', ROUND(ts_diff_seconds/60), ' minutes (', round(ts_diff_seconds/60/60, 2), ' hours)
    Uptime: ', ROUND(100*uptime_diff/NULLIF(ts_diff_seconds, 0), 1),
        '% (Up: ', FLOOR(uptime/(60*60*24)), ' days, ', SEC_TO_TIME(uptime % (60*60*24)), ' hours)

    InnoDB:
        innodb_buffer_pool_size: ', innodb_buffer_pool_size, ' bytes (', ROUND(innodb_buffer_pool_size/(1024*1024), 1), 'MB). Used: ',
            IFNULL(ROUND(100 - 100*innodb_buffer_pool_pages_free/NULLIF(innodb_buffer_pool_pages_total, 0), 1), 'N/A'), '%
        Read hit: ', IFNULL(ROUND(100 - (100*innodb_buffer_pool_reads_diff/NULLIF(innodb_buffer_pool_read_requests_diff, 0)), 2), 'N/A'), '%
        Disk I/O: ', innodb_buffer_pool_reads_psec, ' reads/sec  ', innodb_buffer_pool_pages_flushed_psec, ' flushes/sec
        Estimated log written per hour: ', IFNULL(ROUND(innodb_os_log_written_psec*60*60/1024/1024, 1), 'N/A'), 'MB
        Locks: ', innodb_row_lock_waits_psec, '/sec  current: ', innodb_row_lock_current_waits, '

    MyISAM key cache:
        key_buffer_size: ', key_buffer_size, ' bytes (', ROUND(key_buffer_size/1024/1024, 1), 'MB). Used: ',
            IFNULL(ROUND(100 - 100*(key_blocks_unused * key_cache_block_size)/NULLIF(key_buffer_size, 0), 1), 'N/A'), '%
        Read hit: ',
            IFNULL(ROUND(100 - 100*key_reads_diff/NULLIF(key_read_requests_diff, 0), 1), 'N/A'), '%  Write hit: ',
            IFNULL(ROUND(100 - 100*key_writes_diff/NULLIF(key_write_requests_diff, 0), 1), 'N/A'), '%

    DML:
        SELECT:  ', com_select_psec, '/sec  ', IFNULL(ROUND(100*com_select_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        INSERT:  ', com_insert_psec, '/sec  ', IFNULL(ROUND(100*com_insert_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        UPDATE:  ', com_update_psec, '/sec  ', IFNULL(ROUND(100*com_update_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        DELETE:  ', com_delete_psec, '/sec  ', IFNULL(ROUND(100*com_delete_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        REPLACE: ', com_replace_psec, '/sec  ', IFNULL(ROUND(100*com_replace_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        SET:     ', com_set_option_psec, '/sec  ', IFNULL(ROUND(100*com_set_option_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        COMMIT:  ', com_commit_psec, '/sec  ', IFNULL(ROUND(100*com_commit_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '%
        slow:    ', slow_queries_psec, '/sec  ', IFNULL(ROUND(100*slow_queries_diff/NULLIF(questions_diff, 0), 1), 'N/A'), '% (slow time: ',
            long_query_time ,'sec)

    Selects:
        Full scan: ', select_scan_psec, '/sec  ', IFNULL(ROUND(100*select_scan_diff/NULLIF(com_select_diff, 0), 1), 'N/A'), '%
        Full join: ', select_full_join_psec, '/sec  ', IFNULL(ROUND(100*select_full_join_diff/NULLIF(com_select_diff, 0), 1), 'N/A'), '%
        Range:     ', select_range_psec, '/sec  ', IFNULL(ROUND(100*select_range_diff/NULLIF(com_select_diff, 0), 1), 'N/A'), '%
        Sort merge passes: ', sort_merge_passes_psec, '/sec

    Locks:
        Table locks waited:  ', table_locks_waited_psec, '/sec  ', IFNULL(ROUND(100*table_locks_waited_diff/NULLIF(table_locks_waited_diff + table_locks_immediate_diff, 0), 1), 'N/A'), '%

    Tables:
        Table cache: ', (IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0)), '. Used: ',
            IFNULL(ROUND(100*open_tables/NULLIF(IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0), 0), 1), 'N/A'), '%
        Opened tables: ', opened_tables_psec, '/sec

    Temp tables:
        Max tmp table size:  ', tmp_table_size, ' bytes (', ROUND(tmp_table_size/(1024*1024), 1), 'MB)
        Max heap table size: ', max_heap_table_size, ' bytes (', ROUND(max_heap_table_size/(1024*1024), 1), 'MB)
        Created:             ', created_tmp_tables_psec, '/sec
        Created disk tables: ', created_tmp_disk_tables_psec, '/sec  ',
            IFNULL(ROUND(100*created_tmp_disk_tables_diff/NULLIF(created_tmp_tables_diff, 0), 1), 'N/A'), '%

    Connections:
        Max connections: ', max_connections, '. Max used: ', max_used_connections, '  ',
            IFNULL(ROUND(100*max_used_connections/NULLIF(max_connections, 0), 1), 'N/A'), '%
        Connections: ', connections_psec, '/sec
        Aborted:     ', aborted_connects_psec, '/sec  ',
            IFNULL(ROUND(100*aborted_connects_diff/NULLIF(connections_diff, 0), 1), 'N/A'), '%

    Threads:
        Thread cache: ', thread_cache_size, '. Used: ',
            IFNULL(ROUND(100*threads_cached/NULLIF(thread_cache_size, 0), 1), 'N/A'), '%
        Created: ', threads_created_psec, '/sec

    Replication:
        Master status file number: ', IFNULL(master_status_file_number, 'N/A'), ', position: ', IFNULL(master_status_position, 'N/A'), '
        Relay log space limit: ', IFNULL(max_relay_log_size, 'N/A'), ', free: ', IFNULL(relay_log_space, 'N/A'), '  used: ',
            IFNULL(ROUND(100 - 100*relay_log_space/NULLIF(max_relay_log_size, 0), 1), 'N/A'), '%
        Seconds behind master: ', IFNULL(seconds_behind_master, 'N/A'), '
    ') AS report
        """)

    create_report_google_chart_view([
        ("uptime_percent", "uptime_percent", True, True),

        ("innodb_read_hit_percent", "innodb_read_hit_percent", False, False),
        ("innodb_buffer_pool_reads_psec, innodb_buffer_pool_pages_flushed_psec", "innodb_io", True, False),
        ("innodb_buffer_pool_used_percent", "innodb_buffer_pool_used_percent", True, True),
        ("innodb_estimated_log_mb_written_per_hour", "innodb_estimated_log_mb_written_per_hour", True, False),
        ("innodb_row_lock_waits_psec", "innodb_row_lock_waits_psec", True, False),

        ("mega_bytes_sent_psec, mega_bytes_received_psec", "bytes_io", True, False),

        ("key_buffer_used_percent", "myisam_key_buffer_used_percent", True, True),
        ("key_read_hit_percent, key_read_hit_percent", "myisam_key_hit_ratio", True, True),

        ("com_select_psec, com_insert_psec, com_delete_psec, com_update_psec, com_replace_psec", "DML", True, False),
        ("questions_psec, slow_queries_psec, com_commit_psec, com_set_option_psec", "questions", True, False),

        ("created_tmp_tables_psec, created_tmp_disk_tables_psec", "tmp_tables", True, False),

        ("table_locks_waited_psec", "table_locks_waited_psec", True, False),

        ("table_cache_size, open_tables", "table_cache_use", True, False),
        ("opened_tables_psec", "opened_tables_psec", True, False),

        ("connections_psec, aborted_connects_psec", "connections_psec", True, False),
        ("max_connections, threads_connected", "connections_usage", True, False),

        ("thread_cache_used_percent", "thread_cache_used_percent", True, True),
        ("threads_created_psec", "threads_created_psec", True, False),
        ])

    create_report_html_view("""
        innodb_read_hit_percent, innodb_io, innodb_row_lock_waits_psec, innodb_estimated_log_mb_written_per_hour, innodb_buffer_pool_used_percent,
        myisam_key_buffer_used_percent, myisam_key_hit_ratio,
        bytes_io,
        DML, questions,
        tmp_tables,
        table_locks_waited_psec,
        table_cache_use, opened_tables_psec,
        connections_psec, connections_usage,
        thread_cache_used_percent, threads_created_psec,
        uptime_percent
        """)


def disable_bin_log():
    if options.skip_disable_bin_log:
        return
    try:
        query = "SET SESSION SQL_LOG_BIN=0"
        act_query(query)
    except:
        exit_with_error("Failed to disable binary logging. Either grant the SUPER privilege or use --skip-disable-bin-log")


def collect_status_variables():
    disable_bin_log()

    status_dict = fetch_status_variables()

    column_names = ", ".join(["%s" % column_name for column_name in sorted(status_dict.keys())])
    for column_name in status_dict.keys():
        if status_dict[column_name] is None:
            status_dict[column_name] = "NULL"
        if status_dict[column_name] == "":
            status_dict[column_name] = "NULL"
    variable_values = ", ".join(["%s" % status_dict[column_name] for column_name in sorted(status_dict.keys())])
    query = """INSERT /*! IGNORE */ INTO %s.%s
            (%s)
            VALUES (%s)
    """ % (database_name, table_name,
        column_names,
        variable_values)
    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("New entry added")


def purge_status_variables():
    disable_bin_log()

    query = """DELETE FROM %s.%s WHERE ts < NOW() - INTERVAL %d DAY""" % (database_name, table_name, options.purge_days)
    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("Old entries purged")


def exit_with_error(error_message):
    """
    Notify and exit.
    """
    print_error(error_message)
    sys.exit(1)


try:
    try:
        conn = None
        reuse_conn = True
        (options, args) = parse_options()

        database_name = options.database
        table_name = "status_variables"
        status_dict = {}
        custom_views_columns = {}

        if not database_name:
            exit_with_error("No database specified. Specify with -d or --database")
        if options.purge_days < 1:
            exit_with_error("purge-days must be at least 1")

        conn = open_connection()
        if "create" in args:
            prompt_instructions()
            create_numbers_table()
            create_status_variables_table()
            create_status_variables_views()
            verbose("Table and views created")
        elif "upgrade" in args:
            upgrade_status_variables_table()
            create_status_variables_views()
            verbose("Table and views upgraded")
        else:
            collect_status_variables()
            purge_status_variables()
            verbose("Status variables checkpoint complete")
    except Exception, err:
        print err
        traceback.print_exc()
        sys.exit(1)

finally:
    if conn:
        conn.close()