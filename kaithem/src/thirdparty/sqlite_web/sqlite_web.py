#!/usr/bin/env python

import base64
import datetime
import math
import operator
import os
import re
import sys
import threading
from collections import namedtuple, OrderedDict
from functools import wraps
from functools import reduce
from io import StringIO
from io import TextIOWrapper

from flask.logging import create_logger

import peewee
from peewee import IndexMetadata
from peewee import fn
from playhouse.dataset import DataSet
from playhouse.migrate import migrate


BINARY_TYPES = (bytes, bytearray)


try:
    from flask import (
        Flask,
        abort,
        flash,
        make_response,
        redirect,
        render_template,
        request,
        session,
        url_for,
    )
except ImportError:
    raise RuntimeError(
        "Unable to import flask module. Install by running pip install flask"
    )
try:
    from markupsafe import Markup, escape
except ImportError:
    raise RuntimeError(
        "Unable to import markupsafe module. Install by running"
        " pip install markupsafe"
    )

try:
    from pygments import formatters, highlight, lexers
except ImportError:
    import warnings

    warnings.warn("pygments library not found.", ImportWarning)

    def syntax_highlight(data):
        return "<pre>%s</pre>" % data

else:

    def syntax_highlight(data):
        if not data:
            return ""
        lexer = lexers.get_lexer_by_name("sql")
        # pylint: disable-next=no-member
        formatter = formatters.HtmlFormatter(linenos=False)
        return highlight(data, lexer, formatter)


try:
    from peewee import __version__

    peewee_version = tuple([int(p) for p in __version__.split(".")])
except ImportError:
    raise RuntimeError(
        "Unable to import peewee module. Install by running pip install peewee"
    )
else:
    if peewee_version < (3, 0, 0):
        raise RuntimeError(
            "Peewee >= 3.0.0 is required. Found version %s. "
            "Please update by running pip install --update "
            "peewee" % __version__
        )


CUR_DIR = os.path.realpath(os.path.dirname(__file__))
DEBUG = False
MAX_RESULT_SIZE = 1000
ROWS_PER_PAGE = 50
SECRET_KEY = "sqlite-database-browser-0.1.0"  # pragma: allowlist secret

app = Flask(
    __name__,
    static_folder=os.path.join(CUR_DIR, "static"),
    template_folder=os.path.join(CUR_DIR, "templates"),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
# TODO: This won't work standalone because it references the kaithem file


@app.context_processor
def inject():
    return {"theme_url": "/static/css/barrel.css"}


app.config.from_object(__name__)
LOG = create_logger(app)


all_open_datasets = {}
open_datasets_lock = threading.RLock()


def resolve_dataset(name):
    """Must return the filename URI given the internal URL name, along with whether writing is allowed
    Only called from inside Flask
    """
    raise NotImplementedError()
    return "", False


def get_dataset(name):
    "Return the relevant dataset for this request"
    global resolve_dataset
    name, rw = resolve_dataset(name)
    ro = not rw

    with open_datasets_lock:
        if not name in all_open_datasets:
            if len(all_open_datasets) > 8:
                j = None
                for i in all_open_datasets:
                    j = i

                all_open_datasets[j].close()
                del all_open_datasets[j]

            all_open_datasets[(name, ro)] = open_dataset_from_file(name, ro)

        return all_open_datasets[(name, ro)]


# Database metadata objects.
#

TriggerMetadata = namedtuple("TriggerMetadata", ("name", "sql"))

ViewMetadata = namedtuple("ViewMetadata", ("name", "sql"))

#
# Database helpers.
#


class SqliteDataSet(DataSet):
    @property
    def filename(self):
        db_file = self._database.database
        if db_file.startswith("file:"):
            db_file = db_file[5:]
        return os.path.realpath(db_file.rsplit("?", 1)[0])

    @property
    def is_readonly(self):
        db_file = self._database.database
        return db_file.endswith("?mode=ro")

    @property
    def base_name(self):
        return os.path.basename(self.filename)

    @property
    def created(self):
        stat = os.stat(self.filename)
        return datetime.datetime.fromtimestamp(stat.st_ctime)

    @property
    def modified(self):
        stat = os.stat(self.filename)
        return datetime.datetime.fromtimestamp(stat.st_mtime)

    @property
    def size_on_disk(self):
        stat = os.stat(self.filename)
        return stat.st_size

    def get_indexes(self, table):
        return self._database.get_indexes(table)

    def get_all_indexes(self):
        cursor = self.query(
            "SELECT name, sql FROM sqlite_master WHERE type = ? ORDER BY name",
            ("index",),
        )
        d = cursor.fetchall()
        return [IndexMetadata(row[0], row[1], None, None, None) for row in d]

    def get_columns(self, table):
        return self._database.get_columns(table)

    def get_foreign_keys(self, table):
        return self._database.get_foreign_keys(table)

    def get_triggers(self, table):
        cursor = self.query(
            """SELECT name, sql FROM sqlite_master
            WHERE type = ? AND tbl_name = ?""",
            ("trigger", table),
        )
        return [TriggerMetadata(*row) for row in cursor.fetchall()]

    def get_all_triggers(self):
        cursor = self.query(
            "SELECT name, sql FROM sqlite_master WHERE type = ? ORDER BY name",
            ("trigger",),
        )
        return [TriggerMetadata(*row) for row in cursor.fetchall()]

    def get_table_sql(self, table):
        if not table:
            return

        cursor = self.query(
            "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type IN (?, ?)",
            [table, "table", "view"],
        )
        res = cursor.fetchone()
        if res is not None:
            return res[0]

    def get_view(self, name):
        cursor = self.query(
            "SELECT name, sql FROM sqlite_master WHERE type = ? AND name = ?",
            ("view", name),
        )
        res = cursor.fetchone()
        if res is not None:
            return ViewMetadata(*res)

    def get_all_views(self):
        cursor = self.query(
            "SELECT name, sql FROM sqlite_master WHERE type = ? ORDER BY name",
            ("view",),
        )
        return [ViewMetadata(*row) for row in cursor.fetchall()]

    def get_virtual_tables(self):
        cursor = self.query(
            "SELECT name FROM sqlite_master "
            "WHERE type = ? AND sql LIKE ? "
            "ORDER BY name",
            ("table", "CREATE VIRTUAL TABLE%"),
        )
        return set([row[0] for row in cursor.fetchall()])

    def get_corollary_virtual_tables(self):
        virtual_tables = self.get_virtual_tables()
        suffixes = ["content", "docsize", "segdir", "segments", "stat"]
        return set(
            f"{virtual_table}_{suffix}"
            for suffix in suffixes
            for virtual_table in virtual_tables
        )

    def is_view(self, name):
        cursor = self.query(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("view", name),
        )
        return cursor.fetchone() is not None

    def view_operations(self, name):
        cursor = self.query(
            "SELECT sql FROM sqlite_master WHERE type=? AND tbl_name=?",
            ("trigger", name),
        )
        triggers = [t for (t,) in cursor.fetchall()]
        rgx = re.compile(
            r"CREATE\s+TRIGGER.+?\sINSTEAD\s+OF\s+(INSERT|UPDATE|DELETE)\s", re.I
        )
        operations = set()
        for trigger in triggers:
            operations.update([op.lower() for op in rgx.findall(trigger)])

        return operations


#
# Flask views.
#


@app.route("/")
def file_select(file=None):
    return render_template(
        "index.html",
        sqlite=peewee.sqlite3,
        file=file or "default",
        dataset=get_dataset(file),
    )


@app.route("/<file>/")
def index(file=None):
    return render_template(
        "table_home.html",
        sqlite=peewee.sqlite3,
        file=file or "default",
        dataset=get_dataset(file),
    )


def _query_view(template, file, table=None):
    dataset = get_dataset(file)

    data = []
    data_description = error = row_count = sql = None
    ordering = None

    sql = qsql = request.args.get("sql") or ""

    if "export_json" in request.args:
        ordering = request.args.get("export_ordering")
        export_format = "json"
    elif "export_csv" in request.args:
        ordering = request.args.get("export_ordering")
        export_format = "csv"
    else:
        ordering = request.args.get("ordering")
        export_format = None

    if ordering:
        ordering = int(ordering)
        direction = "DESC" if ordering < 0 else "ASC"
        qsql = "SELECT * FROM (%s) AS _ ORDER BY %d %s" % (
            sql.rstrip(" ;"),
            abs(ordering),
            direction,
        )
    else:
        ordering = None

    if table:
        default_sql = 'SELECT * FROM "%s"' % table
        model_class = dataset[table].model_class
    else:
        default_sql = ""
        model_class = dataset._base_model

    if qsql:
        if export_format:
            query = model_class.raw(qsql).dicts()
            return export(file, query, export_format, table)

        try:
            cursor = dataset.query(qsql)
        except Exception as exc:
            error = str(exc)
            LOG.exception("Error in user-submitted query.")
        else:
            data = cursor.fetchall()[: app.config["MAX_RESULT_SIZE"]]
            data_description = cursor.description
            row_count = cursor.rowcount

    return render_template(
        template,
        data=data,
        data_description=data_description,
        default_sql=default_sql,
        error=error,
        ordering=ordering,
        query_images=get_query_images(),
        row_count=row_count,
        sql=sql,
        table=table,
        file=file,
        dataset=dataset,
        table_sql=dataset.get_table_sql(table),
    )


@app.route("/<file>/query/", methods=["GET"])
def generic_query(file):
    return _query_view("query.html", file)


def require_table(fn):
    @wraps(fn)
    def inner(file, table, *args, **kwargs):
        if table not in get_dataset(file).tables:
            abort(404)
        return fn(file, table, *args, **kwargs)

    return inner


@app.route("/<file>/create-table/", methods=["POST"])
def table_create(file):
    table = (request.form.get("table_name") or "").strip()
    if not table:
        flash("Table name is required.", "danger")
        dest = request.form.get("redirect") or url_for("index")
        if not dest.startswith("/"):
            dest = "/" + dest
        return redirect(dest)

    try:
        get_dataset(file)[table]
    except Exception as exc:
        flash("Error: %s" % str(exc), "danger")
        LOG.exception("Error attempting to create table.")
    return redirect(url_for("table_import", table=table, file=file))


@app.route("/<file>/<table>/structure")
@require_table
def table_structure(file, table):
    dataset = get_dataset(file)
    ds_table = dataset[table]
    model_class = ds_table.model_class

    return render_template(
        "table_structure.html",
        file=file,
        dataset=dataset,
        columns=dataset.get_columns(table),
        ds_table=ds_table,
        foreign_keys=dataset.get_foreign_keys(table),
        indexes=dataset.get_indexes(table),
        model_class=model_class,
        table=table,
        table_sql=dataset.get_table_sql(table),
        triggers=dataset.get_triggers(table),
    )


def get_request_data():
    if request.method == "POST":
        return request.form
    return request.args


@app.route("/<file>/<table>/add-column/", methods=["GET", "POST"])
@require_table
def add_column(file, table):
    class JsonField(peewee.TextField):
        field_type = "JSON"

    column_mapping = OrderedDict(
        (
            ("TEXT", peewee.TextField),
            ("INTEGER", peewee.IntegerField),
            ("REAL", peewee.FloatField),
            ("BLOB", peewee.BlobField),
            ("JSON", JsonField),
            ("BOOL", peewee.BooleanField),
            ("DATETIME", peewee.DateTimeField),
            ("DATE", peewee.DateField),
            ("DECIMAL", peewee.DecimalField),
            ("TIME", peewee.TimeField),
            ("VARCHAR", peewee.CharField),
        )
    )

    request_data = get_request_data()
    col_type = request_data.get("type")
    name = request_data.get("name", "")
    dataset = get_dataset(file)

    fk_table = request_data.get("fk_table")
    fk_field = request_data.get("fk_field")
    nullable = request_data.get("option_null", False)

    use_default = request_data.get("use_default", False)
    default = request_data.get("default_value")

    if not use_default:
        default = None

    if request.method == "POST":
        if name and col_type in column_mapping:
            try:
                if not fk_table:
                    col = column_mapping[col_type](null=nullable, default=default)
                else:
                    fk = dataset._models[fk_table]._meta.fields[fk_field]
                    col = peewee.ForeignKeyField(
                        dataset._models[fk_table],
                        field=fk,
                        null=nullable,
                        default=default,
                    )

                migrate(dataset._migrator.add_column(table, name, col))
            except Exception as exc:
                flash('Error attempting to add column "%s": %s' % (name, exc), "danger")
                LOG.exception("Error attempting to add column.")
            else:
                flash('Column "%s" was added successfully!' % name, "success")
                dataset.update_cache(table)
                return redirect(url_for("table_structure", file=file, table=table))
        else:
            flash("Name and column type are required.", "danger")

    return render_template(
        "add_column.html",
        file=file,
        dataset=dataset,
        col_type=col_type,
        column_mapping=column_mapping,
        name=name,
        table=table,
        table_sql=dataset.get_table_sql(table),
    )


@app.route("/<file>/<table>/drop-column/", methods=["GET", "POST"])
@require_table
def drop_column(file, table):
    request_data = get_request_data()
    name = request_data.get("name", "")
    dataset = get_dataset(file)
    columns = dataset.get_columns(table)
    column_names = [column.name for column in columns]

    if request.method == "POST":
        if name in column_names:
            try:
                migrate(dataset._migrator.drop_column(table, name))
            except Exception as exc:
                flash(
                    'Error attempting to drop column "%s": %s' % (name, exc), "danger"
                )
                LOG.exception("Error attempting to drop column.")
            else:
                flash('Column "%s" was dropped successfully!' % name, "success")
                dataset.update_cache(table)
                return redirect(url_for("table_structure", file=file, table=table))
        else:
            flash("Name is required.", "danger")

    return render_template(
        "drop_column.html",
        file=file,
        dataset=dataset,
        columns=columns,
        column_names=column_names,
        name=name,
        table=table,
    )


@app.route("/<file>/<table>/rename-column/", methods=["GET", "POST"])
@require_table
def rename_column(file, table):
    request_data = get_request_data()
    rename = request_data.get("rename", "")
    rename_to = request_data.get("rename_to", "")
    dataset = get_dataset(file)

    columns = dataset.get_columns(table)
    column_names = [column.name for column in columns]

    if request.method == "POST":
        if (rename in column_names) and (rename_to not in column_names):
            try:
                migrate(dataset._migrator.rename_column(table, rename, rename_to))
            except Exception as exc:
                flash(
                    'Error attempting to rename column "%s": %s' % (rename, exc),
                    "danger",
                )
                LOG.exception("Error attempting to rename column.")
            else:
                flash('Column "%s" was renamed successfully!' % rename, "success")
                dataset.update_cache(table)
                return redirect(url_for("table_structure", file=file, table=table))
        else:
            flash(
                "Column name is required and cannot conflict with an "
                "existing column's name.",
                "danger",
            )

    return render_template(
        "rename_column.html",
        file=file,
        dataset=dataset,
        columns=columns,
        column_names=column_names,
        rename=rename,
        rename_to=rename_to,
        table=table,
    )


@app.route("/<file>/<table>/add-index/", methods=["GET", "POST"])
@require_table
def add_index(file, table):
    request_data = get_request_data()
    indexed_columns = request_data.getlist("indexed_columns")
    unique = bool(request_data.get("unique"))
    dataset = get_dataset(file)
    columns = get_dataset(file).get_columns(table)

    if request.method == "POST":
        if indexed_columns:
            try:
                migrate(
                    get_dataset(file)._migrator.add_index(
                        table, indexed_columns, unique
                    )
                )
            except Exception as exc:
                flash("Error attempting to create index: %s" % exc, "danger")
                LOG.exception("Error attempting to create index.")
            else:
                flash("Index created successfully.", "success")
                return redirect(url_for("table_structure", file=file, table=table))
        else:
            flash("One or more columns must be selected.", "danger")

    return render_template(
        "add_index.html",
        file=file,
        dataset=dataset,
        columns=columns,
        indexed_columns=indexed_columns,
        table=table,
        unique=unique,
    )


@app.route("/<file>/<table>/drop-index/", methods=["GET", "POST"])
@require_table
def drop_index(file, table):
    request_data = get_request_data()
    name = request_data.get("name", "")
    indexes = get_dataset(file).get_indexes(table)
    index_names = [index.name for index in indexes]
    dataset = get_dataset(file)

    if request.method == "POST":
        if name in index_names:
            try:
                migrate(indexes._migrator.drop_index(table, name))
            except Exception as exc:
                flash("Error attempting to drop index: %s" % exc, "danger")
                LOG.exception("Error attempting to drop index.")
            else:
                flash('Index "%s" was dropped successfully!' % name, "success")
                return redirect(url_for("table_structure", file=file, table=table))
        else:
            flash("Index name is required.", "danger")

    return render_template(
        "drop_index.html",
        file=file,
        dataset=dataset,
        indexes=indexes,
        index_names=index_names,
        name=name,
        table=table,
    )


@app.route("/<file>/<table>/drop-trigger/", methods=["GET", "POST"])
@require_table
def drop_trigger(file, table):
    request_data = get_request_data()
    name = request_data.get("name", "")
    dataset = get_dataset(file)
    triggers = dataset.get_triggers(table)
    trigger_names = [trigger.name for trigger in triggers]

    if request.method == "POST":
        if name in trigger_names:
            try:
                dataset.query('DROP TRIGGER "%s";' % name)
            except Exception as exc:
                flash("Error attempting to drop trigger: %s" % exc, "danger")
                LOG.exception("Error attempting to drop trigger.")
            else:
                flash('Trigger "%s" was dropped successfully!' % name, "success")
                return redirect(url_for("table_structure", table=table, file=file))
        else:
            flash("Trigger name is required.", "danger")

    return render_template(
        "drop_trigger.html",
        file=file,
        dataset=dataset,
        triggers=triggers,
        trigger_names=trigger_names,
        name=name,
        table=table,
    )


def get_all_backlinks(file):
    """Return a dict of (table, field) to [(table, field)] where the items in the list are foreign keys linking back to the main dict key
    Used for things like finding all orders for a given customer
    """

    backlinks = {}

    dataset = get_dataset(file)
    for table in dataset.tables:
        for column in dataset.get_columns(table):
            field = dataset._models[table]._meta.columns[column.name]
            if isinstance(field, peewee.ForeignKeyField):
                k = field.rel_model._meta.table_name, field.rel_field.name
                l = backlinks.get(k, list())
                backlinks[k] = l
                l.append((table, column.name))

    return backlinks


def make_fk_summary_function(field):
    """Given  a fk field, make a funtcion that takes a row from the parent table and summarizes it
    for display."""
    # We are going to make a summary of the table.
    # Basically, first try to get something named name or title
    # then try the first text field, finally try all the fields.

    parent = field.rel_model

    include_columns = []
    for j in parent._meta.columns:
        if not j == field.rel_field.name:
            if j in ("name", "title"):
                include_columns.append(j)

    for j in parent._meta.columns:
        if not j == field.rel_field.name:
            if isinstance(parent._meta.columns[j], peewee.TextField):
                include_columns.append(j)

    for j in parent._meta.columns:
        if not j == field.rel_field.name:
            if not isinstance(parent._meta.columns[j], peewee.ForeignKeyField):
                include_columns.append(j)

    def format_for_display(fk_field_value):
        q = parent.select().where(field.rel_field == fk_field_value)

        for j in q:
            summary = ""
            for k in include_columns:
                d = str(getattr(j, k))
                if (not summary) or (d and (len(d) < len(summary))):
                    summary = d
                if summary and len(summary) < 32:
                    break

            return summary.strip()[:32]

        return fk_field_value

    return format_for_display


@app.route("/<file>/<table>/", methods=["GET", "POST"])
@require_table
def table_content(file, table):
    page_number = request.args.get("page") or ""
    if page_number == "last":
        page_number = "1000000"
    page_number = int(page_number) if page_number.isdigit() else 1
    dataset = get_dataset(file)
    dataset.update_cache(table)
    ds_table = dataset[table]
    model = ds_table.model_class
    total_rows = ds_table.all().count()

    columns = []
    col_dict = {}
    row = {}
    auto_fields = []
    foreign_key_fields = {}
    foreign_key_display_functions = {}

    for column in dataset.get_columns(table):
        field = model._meta.columns[column.name]
        if isinstance(field, peewee.AutoField):
            auto_fields.append(column.name)
        if isinstance(field, peewee.ForeignKeyField):
            foreign_key_fields[column.name] = field

        columns.append(column)
        col_dict[column.name] = column
        row[column.name] = ""

    for idx, foreignkeyfield in foreign_key_fields.items():
        foreign_key_display_functions[idx] = make_fk_summary_function(foreignkeyfield)

    # with and without the prefix
    example = {}
    example2 = {}
    for key, value in request.args.items():
        if not key.startswith("match_"):
            continue
        if value:
            if key[len("match_") :] not in col_dict:
                continue
            column = col_dict[key[len("match_") :]]
            example2[column.name] = value
            example[key] = value

            field = model._meta.columns[column.name]
            value, err = minimal_validate_field(field, value)
            if err:
                raise RuntimeError(err)

    rows_per_page = app.config["ROWS_PER_PAGE"]
    total_pages = max(1, int(math.ceil(total_rows / float(rows_per_page))))

    # Restrict bounds, approx
    page_number = min(page_number, total_pages)
    page_number = max(page_number, 1)

    if example:
        query = ds_table.find(**example2).paginate(page_number, rows_per_page)
    else:
        query = ds_table.all().paginate(page_number, rows_per_page)

    previous_page = page_number - 1 if page_number > 1 else None
    next_page = page_number + 1 if page_number < total_pages else None

    counts = {}
    if total_rows < 2**14:
        for i in columns:
            if model._meta.columns[i.name].field_type in (
                "REAL",
                "INTEGER",
                "INT",
                "DECIMAL",
            ):
                if not isinstance(model._meta.columns[i.name], peewee.ForeignKeyField):
                    x = (
                        ds_table.find(**example2)
                        .select(fn.SUM(model._meta.columns[i.name]))
                        .scalar()
                    )
                    counts[i.name] = x

    ordering = request.args.get("ordering")
    if ordering:
        field = model._meta.columns[ordering.lstrip("-")]
        if ordering.startswith("-"):
            field = field.desc()
        query = query.order_by(field)

    session["%s.last_viewed" % table] = (page_number, ordering)

    field_names = ds_table.columns

    backlinks = get_all_backlinks(file)

    backlinks = {i: backlinks[i] for i in backlinks if i[0] == table}

    return render_template(
        "table_content.html",
        backlinks=backlinks,
        file=file,
        columns=columns,
        counts=counts,
        dataset=dataset,
        ds_table=ds_table,
        field_names=field_names,
        auto_fields=auto_fields,
        foreign_key_display_functions=foreign_key_display_functions,
        next_page=next_page,
        ordering=ordering,
        page=page_number,
        example=example,
        example2=example2,
        previous_page=previous_page,
        query=query,
        table=table,
        table_pk=model._meta.primary_key,
        table_sql=dataset.get_table_sql(table),
        total_pages=total_pages,
        total_rows=total_rows,
        foreign_key_fields=foreign_key_fields,
        str=str,
    )


def minimal_validate_field(field, value):
    if value.lower().strip() == "null":
        value = None
    if value is None and not field.null:
        return "NULL", "Column does not allow NULL values."
    if value is None:
        return None, None
    if isinstance(field, peewee.IntegerField) and not value.isdigit():
        return value, "Value is not a number."
    elif isinstance(field, peewee.FloatField):
        try:
            _ = float(value)
        except Exception:
            return value, "Value is not a numeric/real."
    elif isinstance(field, peewee.BooleanField):
        if value.lower() not in ("1", "0", "true", "false", "t", "f"):
            return value, "Value must be 1, 0, true, false, t or f."
        value = True if value.lower() in ("1", "t", "true") else False
    elif isinstance(field, peewee.BlobField):
        try:
            value = base64.b64decode(value)
        except Exception:
            return value, "Value must be base64-encoded binary data."
    try:
        field.db_value(value)
    except Exception as exc:
        return value, str(exc)

    return value, None


@app.route("/<file>/<table>/insert/", methods=["GET", "POST"])
@require_table
def table_insert(file, table):
    dataset = get_dataset(file)
    dataset.update_cache(table)
    model = dataset[table].model_class

    columns = []
    col_dict = {}
    row = {}
    for column in dataset.get_columns(table):
        field = model._meta.columns[column.name]
        if isinstance(field, peewee.AutoField):
            continue
        columns.append(column)
        col_dict[column.name] = column
        row[column.name] = ""

    edited = set()
    errors = {}
    if request.method == "POST":
        insert = {}
        for key, value in request.form.items():
            if key not in col_dict:
                continue
            column = col_dict[key]
            edited.add(column.name)
            row[column.name] = value

            field = model._meta.columns[column.name]
            value, err = minimal_validate_field(field, value)
            if err:
                errors[key] = err
            else:
                insert[field] = value

        if errors:
            flash("One or more errors prevented the row being inserted.", "danger")
        elif insert:
            try:
                with dataset.transaction():
                    n = model.insert(insert).execute()
            except Exception as exc:
                flash("Insert failed: %s" % exc, "danger")
                LOG.exception("Error attempting to insert row into %s.", table)
            else:
                flash("Successfully inserted record (%s)." % n, "success")
                return redirect(
                    url_for("table_content", file=file, table=table, page="last")
                )
        else:
            flash("No data was specified to be inserted.", "warning")
    else:
        edited = set(col_dict)  # Make all fields editable on load.

    return render_template(
        "table_insert.html",
        file=file,
        dataset=dataset,
        columns=columns,
        edited=edited,
        errors=errors,
        model=model,
        row=row,
        table=table,
    )


def redirect_to_previous(file, table):
    page_ordering = session.get("%s.last_viewed" % table)
    if not page_ordering:
        return redirect(url_for("table_content", file=file, table=table))
    page, ordering = page_ordering
    kw = {}
    if page and page != 1:
        kw["page"] = page
    if ordering:
        kw["ordering"] = ordering
    return redirect(url_for("table_content", file=file, table=table, **kw))


@app.route("/<file>/<table>/update/<pk>/", methods=["GET", "POST"])
@require_table
def table_update(file, table, pk):
    dataset = get_dataset(file)
    dataset.update_cache(table)
    model = dataset[table].model_class
    table_pk = model._meta.primary_key
    if not table_pk:
        flash("Table must have a primary key to perform update.", "danger")
        return redirect(url_for("table_content", file=file, table=table))
    elif pk == "__uneditable__":
        flash("Could not encode primary key to perform update.", "danger")
        return redirect(url_for("table_content", file=file, table=table))

    expr = decode_pk(model, pk)
    try:
        obj = model.get(expr)
    except model.DoesNotExist:
        pk_repr = pk_display(table_pk, pk)
        flash("Could not fetch row with primary-key %s." % str(pk_repr), "danger")
        return redirect(url_for("table_content", file=file, table=table))

    columns = dataset.get_columns(table)
    col_dict = {}
    row = {}
    for column in columns:
        value = getattr(obj, column.name)
        if value is None:
            row[column.name] = None
        elif column.data_type.lower() == "blob":
            row[column.name] = base64.b64encode(value).decode("utf8")
        else:
            row[column.name] = value

        col_dict[column.name] = column

    edited = set()
    errors = {}
    if request.method == "POST":
        update = {}
        for key, value in request.form.items():
            if key not in col_dict:
                continue
            column = col_dict[key]
            edited.add(column.name)
            row[column.name] = value

            field = model._meta.columns[column.name]
            value, err = minimal_validate_field(field, value)
            if err:
                errors[key] = err
            else:
                update[field] = value

        if errors:
            flash("One or more errors prevented the row being updated.", "danger")
        elif update:
            try:
                with dataset.transaction():
                    n = model.update(update).where(expr).execute()
            except Exception as exc:
                flash("Update failed: %s" % exc, "danger")
                LOG.exception("Error attempting to update row from %s.", table)
            else:
                flash("Successfully updated %s record." % n, "success")
                return redirect_to_previous(file, table)
        else:
            flash("No data was specified to be updated.", "warning")

    return render_template(
        "table_update.html",
        file=file,
        dataset=dataset,
        columns=columns,
        edited=edited,
        errors=errors,
        model=model,
        pk=pk,
        row=row,
        table=table,
        table_pk=model._meta.primary_key,
    )


@app.route("/<file>/<table>/delete/<pk>/", methods=["GET", "POST"])
@require_table
def table_delete(file, table, pk):
    dataset = get_dataset(file)
    dataset.update_cache(table)
    model = dataset[table].model_class
    table_pk = model._meta.primary_key
    if not table_pk:
        flash("Table must have a primary key to perform delete.", "danger")
        return redirect(url_for("table_content", file=file, table=table))
    elif pk == "__uneditable__":
        flash("Could not encode primary key to perform delete.", "danger")
        return redirect(url_for("table_content", file=file, table=table))

    expr = decode_pk(model, pk)
    try:
        row = model.select().where(expr).dicts().get()
    except model.DoesNotExist:
        pk_repr = pk_display(table_pk, pk)
        flash("Could not fetch row with primary-key %s." % str(pk_repr), "danger")
        return redirect(url_for("table_content", file=file, table=table))

    if request.method == "POST":
        try:
            with dataset.transaction():
                n = model.delete().where(expr).execute()
        except Exception as exc:
            flash("Delete failed: %s" % exc, "danger")
            LOG.exception("Error attempting to delete row from %s.", table)
        else:
            flash("Successfully deleted %s record." % n, "success")
            return redirect_to_previous(file, table)

    return render_template(
        "table_delete.html",
        column_names=[c.name for c in dataset.get_columns(table)],
        file=file,
        dataset=dataset,
        model=model,
        pk=pk,
        row=row,
        table=table,
        table_pk=table_pk,
    )


@app.route("/<file>/<table>/query/", methods=["GET"])
@require_table
def table_query(file, table):
    return _query_view("table_query.html", file, table)


def export(file, query, export_format, table=None):
    buf = StringIO()
    if export_format == "json":
        kwargs = {"indent": 2}
        filename = "export.json"
        mimetype = "text/javascript"
    else:
        kwargs = {}
        filename = "export.csv"
        mimetype = "text/csv"

    if table:
        filename = "%s-%s" % (table, filename)

    # Avoid any special chars in export filename.
    filename = re.sub(r"[^\w\d\-\.]+", "", filename)

    get_dataset(file).freeze(query, export_format, file_obj=buf, **kwargs)

    response_data = buf.getvalue()
    response = make_response(response_data)
    response.headers["Content-Length"] = len(response_data)
    response.headers["Content-Type"] = mimetype
    response.headers["Content-Disposition"] = 'attachment; filename="%s"' % (filename)
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "public"
    return response


@app.route("/<file>/<table>/export/", methods=["GET", "POST"])
@require_table
def table_export(file, table):
    dataset = get_dataset(file)
    columns = dataset.get_columns(table)
    if request.method == "POST":
        export_format = request.form.get("export_format") or "json"
        col_dict = {c.name: c for c in columns}
        selected = [c for c in (request.form.getlist("columns") or []) if c in col_dict]
        if not selected:
            flash("Please select one or more columns to export.", "danger")
        else:
            model = dataset[table].model_class
            fields = [model._meta.columns[c] for c in selected]
            query = model.select(*fields).dicts()
            try:
                return export(file, query, export_format, table)
            except Exception as exc:
                flash("Error generating export: %s" % exc, "danger")
                LOG.exception("Error generating export.")

    return render_template(
        "table_export.html", columns=columns, table=table, file=file, dataset=dataset
    )


@app.route("/<file>/<table>/import/", methods=["GET", "POST"])
@require_table
def table_import(file, table):
    count = None
    dataset = get_dataset(file)
    request_data = get_request_data()
    strict = bool(request_data.get("strict"))
    if request.method == "POST":
        file_obj = request.files.get("file")
        if not file_obj:
            flash("Please select an import file.", "danger")
        elif not file_obj.filename.lower().endswith((".csv", ".json")):
            flash("Unsupported file-type. Must be a .json or .csv file.", "danger")
        else:
            if file_obj.filename.lower().endswith(".json"):
                file_format = "json"
            else:
                file_format = "csv"

            # Here we need to translate the file stream. Werkzeug uses a
            # spooled temporary file opened in wb+ mode, which is not
            # compatible with Python's CSV module. We'd need to reach pretty
            # far into Flask's internals to modify this behavior, so instead
            # we'll just translate the stream into utf8-decoded unicode.
            try:
                stream = TextIOWrapper(file_obj, encoding="utf8")
            except AttributeError:
                # The SpooledTemporaryFile used by werkzeug does not
                # implement an API that the TextIOWrapper expects, so we'll
                # just consume the whole damn thing and decode it.
                # Fixed in werkzeug 0.15.
                stream = StringIO(file_obj.read().decode("utf8"))

            try:
                with dataset.transaction():
                    count = dataset.thaw(
                        table, format=file_format, file_obj=stream, strict=strict
                    )
            except Exception as exc:
                flash("Error importing file: %s" % exc, "danger")
                LOG.exception("Error importing file.")
            else:
                flash(
                    "Successfully imported %s objects from %s."
                    % (count, file_obj.filename),
                    "success",
                )
                return redirect(url_for("table_content", file=file, table=table))

    return render_template(
        "table_import.html",
        count=count,
        strict=strict,
        table=table,
        file=file,
        dataset=dataset,
    )


@app.route("/<file>/<table>/drop/", methods=["GET", "POST"])
@require_table
def drop_table(file, table):
    dataset = get_dataset(file)
    is_view = any(v.name == table for v in dataset.get_all_views())
    label = "view" if is_view else "table"
    if request.method == "POST":
        try:
            if is_view:
                dataset.query('DROP VIEW "%s";' % table)
            else:
                model_class = dataset[table].model_class
                model_class.drop_table()
        except Exception:
            flash('Error attempting to drop %s "%s".' % (label, table), "danger")
            LOG.exception('Error attempting to drop %s "%s".', label, table)
        else:
            dataset.update_cache()  # Update all tables.
            flash(
                '%s "%s" dropped successfully.'
                % ("view" if is_view else "table", table),
                "success",
            )
            return redirect(
                url_for(
                    "index",
                    file=file,
                )
            )

    return render_template(
        "drop_table.html", is_view=is_view, table=table, file=file, dataset=dataset
    )


@app.template_filter("format_index")
def format_index(index_sql):
    split_regex = re.compile(r"\bon\b", re.I)
    if not split_regex.search(index_sql):
        return index_sql

    create, definition = split_regex.split(index_sql)
    return "\nON ".join((create.strip(), definition.strip()))


@app.template_filter("encode_pk")
def encode_pk(row, pk):
    if isinstance(pk, peewee.CompositeKey):
        try:
            return ":::".join([str(row[k]) for k in pk.field_names])
        except Exception:
            return "__uneditable__"
    return row[pk.column_name]


def decode_pk(model, pk_data):
    pk = model._meta.primary_key
    if isinstance(pk, peewee.CompositeKey):
        fields = [pk.model._meta.columns[f] for f in pk.field_names]
        values = pk_data.split(":::")
        expressions = [(f == v) for f, v in zip(fields, values)]
        return reduce(operator.and_, expressions)
    return pk == pk_data


@app.template_filter("pk_display")
def pk_display(table_pk, pk):
    if isinstance(table_pk, peewee.CompositeKey):
        return tuple(pk.split(":::"))
    return pk


@app.template_filter("value_filter")
def value_filter(value, max_length=50):
    if isinstance(value, (int, float)):
        return value

    if isinstance(value, BINARY_TYPES):
        if not isinstance(value, (bytes, bytearray)):
            value = bytes(value)  # Handle `buffer` type.
        value = base64.b64encode(value)[:1024].decode("utf8")
    if isinstance(value, str):
        value = escape(value)
        if len(value) > max_length:
            return (
                '<span class="truncated">%s</span> '
                '<span class="full" style="display:none;">%s</span>'
                '<a class="toggle-value" href="#">...</a>'
            ) % (value[:max_length], value)
    return value


column_re = re.compile(r"(.+?)\((.+)\)", re.S)
column_split_re = re.compile(r"(?:[^,(]|\([^)]*\))+")


def _format_create_table(sql):
    create_table, column_list = column_re.search(sql).groups()
    columns = [
        "  %s" % column.strip()
        for column in column_split_re.findall(column_list)
        if column.strip()
    ]
    return "%s (\n%s\n)" % (create_table, ",\n".join(columns))


@app.template_filter()
def format_create_table(sql):
    try:
        return _format_create_table(sql)
    except Exception:
        return sql


@app.template_filter("highlight")
def highlight_filter(data):
    return Markup(syntax_highlight(data))


def get_query_images():
    accum = []
    image_dir = os.path.join(app.static_folder, "img")
    if not os.path.exists(image_dir):
        return accum
    for filename in sorted(os.listdir(image_dir)):
        basename = os.path.splitext(os.path.basename(filename))[0]
        parts = basename.split("-")
        accum.append((parts, "img/" + filename))
    return accum


#
# Flask application helpers.
#


@app.context_processor
def _general():
    return {
        # "dataset": get_dataset(file),
        "login_required": bool(app.config.get("PASSWORD")),
    }


@app.context_processor
def _now():
    return {"now": datetime.datetime.now()}


@app.before_request
def _check_csrf():
    if "Origin" in request.headers:
        if request.headers["Origin"]:
            if not request.headers["Origin"].split("//")[-1] == request.host:
                raise RuntimeError("CSRF not allowed")


class PrefixMiddleware(object):
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = "/%s" % prefix.strip("/")
        self.prefix_len = len(self.prefix)

    def __call__(self, environ, start_response):
        if environ["PATH_INFO"].startswith(self.prefix):
            environ["PATH_INFO"] = environ["PATH_INFO"][self.prefix_len :]
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response("404", [("Content-Type", "text/plain")])
            return ["URL does not match application prefix.".encode()]


def die(msg, exit_code=1):
    sys.stderr.write("%s\n" % msg)
    sys.stderr.flush()
    sys.exit(exit_code)


extensions = None


def open_dataset_from_file(filename, read_only=False):
    pragmas = {"foreign_keys": 1}

    dataset_kw = {}
    if peewee_version >= (3, 14, 9):
        dataset_kw["include_views"] = True

    if read_only:
        if sys.version_info < (3, 4, 0):
            die("Python 3.4.0 or newer is required for read-only access.")
        if peewee_version < (3, 5, 1):
            die("Peewee 3.5.1 or newer is required for read-only access.")
        db = peewee.SqliteDatabase(
            "file:%s?mode=ro" % filename, uri=True, pragmas=pragmas
        )
        try:
            db.connect()
        except peewee.OperationalError:
            die(
                "Unable to open database file in read-only mode. Ensure that "
                "the database exists in order to use read-only mode."
            )
        db.close()
        _dataset = SqliteDataSet(db, bare_fields=True, **dataset_kw)
    else:
        db = peewee.SqliteDatabase("file:%s" % filename, uri=True, pragmas=pragmas)
        _dataset = SqliteDataSet(db, bare_fields=True, **dataset_kw)
        with open_datasets_lock:
            all_open_datasets[filename] = _dataset

    if extensions:
        for ext in extensions:
            _dataset._database.load_extension(ext)

    return _dataset


def initialize_app(url_prefix=None, use_extensions=None):
    global extensions
    extensions = use_extensions

    if url_prefix:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=url_prefix)
