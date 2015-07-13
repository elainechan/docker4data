#!/usr/bin/env python

'''
Download data based off of a data.json.  Skips download if metadata matches.

    scripts/build.py <url> <s3bucket> <tmp path>
'''

import requests
import sys
import os
import subprocess
import hashlib
import json
import logging

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler(sys.stderr))


def shell(cmd):
    """
    Run a shell command convenience function.
    """
    LOGGER.info(cmd)
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)


def run_postgres_script(script_path):
    """
    Run some psql code.
    """
    return shell('gosu postgres psql < {}'.format(script_path))


def run_remote_script(desc, tmp_dir, env_vars=None):
    """
    Run some remote code -- downloads and executes.  Supported are postgres
    and bash.
    """
    script_type = desc[u'type']
    url = desc[u'@id']
    script_name = 'script'
    script_path = os.path.join(tmp_dir, script_name)
    with open(script_path, 'w') as script:
        script.write(requests.get(url).content)

    if script_type == 'postgres':
        run_postgres_script(script_path)
    elif script_type in ('bash', ):
        env_vars = ' '.join([k + '=' + v for k, v in (env_vars or {}).items()])
        shell('cd {} && {} {} {}'.format(tmp_dir, env_vars, script_type, script_name))
    else:
        raise Exception("Script type '{}' not supported".format(script_type))


def generate_schema(tmpname, schema):
    """
    Generate a schema dynamically in cases where it doesn't exist already.
    """
    columns = [u'\t"{}"\t{}'.format(c['name'], c['type']) for c in schema['columns']]
    return u'CREATE TABLE "{tmpname}" (\n{columns}\n);\n'.format(
        tmpname=tmpname, columns=',\n'.join(columns))


def wget_download(url, name, tmp_dir):
    """
    Download a URL and save it in file called 'name'.
    """
    outfile_path = os.path.join(tmp_dir, name)
    shell("wget -q -O {} {}".format(outfile_path, url))
    return outfile_path


def get_current_digest(metadata):
    """
    Calculate a digest from existing metadata.
    """
    # No way to tell if no original metadata embedded
    if 'metadata' not in metadata:
        return ''

    # Can only tell for Socrata right now
    if 'socrata' not in metadata['metadata']:
        return ''

    try:
        socrata_metadata = requests.get(metadata['metadata']['socrata']['@id']).json()
    except ValueError:
        LOGGER.warn('bad socrata metadata for %s', metadata)

    # Can't hash the entire thing because downloadCount changes!  For now
    # just use rowsUpdatedAt, or viewLastModified
    last_modified = socrata_metadata.get(u'rowsUpdatedAt',
                                         socrata_metadata.get(u'viewLastModified'))
    if not last_modified:
        return ''

    current_digest = hashlib.sha1(unicode(last_modified)).hexdigest()
    #LOGGER.info('metadata hexdigest: %s', current_digest)
    return current_digest


def get_old_digest(s3_bucket, name):
    """
    Determine the prior digest, if any, from previous builds.
    """
    try:
        resp = shell(
            'aws s3api head-object --bucket {} --key {}'.format(s3_bucket, name))
        old_headers = json.loads(resp)
    except subprocess.CalledProcessError:
        return None

    if 'Metadata' not in old_headers:
        return None

    if 'metadata_sha1_hexdigest' not in old_headers['Metadata']:
        return None

    return old_headers['Metadata']['metadata_sha1_hexdigest']


def pgload_import(tmpname, schema_name, dataset_name, data_path, load_format, tmp_dir): #pylint: disable=too-many-arguments
    """
    Import a dataset via pgload.
    """
    pgload_path = os.path.join(tmp_dir, 'pgloader.load')
    format_type = load_format.get('type', 'csv')
    default_sep = '\t' if format_type == 'tsv' else ','
    separator = load_format.get('separator', default_sep)
    with open(pgload_path, 'w') as pgload:
        pgload.write('''
LOAD CSV FROM stdin
  INTO postgresql://postgres@localhost/postgres?tablename={tmpname}
  WITH skip header = 1,
       batch rows = 10000,
       fields terminated by '{sep}',
       batch concurrency = 1,
       batch rows = 1000,
       batch size = 5MB
  SET work_mem to '16MB',
      maintenance_work_mem to '100MB'
  AFTER LOAD DO
       $$ CREATE SCHEMA IF NOT EXISTS "{schema_name}"; $$,
       $$ ALTER TABLE "{tmpname}"
            SET SCHEMA "{schema_name}"; $$,
       $$ ALTER TABLE "{schema_name}"."{tmpname}"
            RENAME TO "{dataset_name}";
       $$;
'''.format(tmpname=tmpname, schema_name=schema_name, dataset_name=dataset_name, sep=separator))

    script = 'gosu postgres gunzip -c {} | tail -n +2 | '.format(data_path)
    if bool(load_format.get('unique', False)):
        script += 'sort | uniq | '
    script += 'pgloader {}'.format(pgload_path)
    shell(script)


def ogr2ogr_import(schema_name, dataset_name, tmp_dir):
    """
    Use ogr2ogr to load a shapefile into the database.
    """
    path = shell(u'ls {}/*/*.shp'.format(tmp_dir))
    name = u'.'.join(path.split(os.path.sep)[-1].split('.')[0:-1]).lower()
    shell(u'gosu postgres ogr2ogr -nlt GEOMETRY -t_srs EPSG:4326 -overwrite '
          u'-f "PostgreSQL" PG:dbname=postgres {path}'.format(path=path))
    shell(u"gosu postgres psql -c 'CREATE SCHEMA IF NOT EXISTS \"{schema_name}\"'".format(
        schema_name=schema_name))
    shell(u"gosu postgres psql -c 'ALTER TABLE \"{name}\" SET SCHEMA \"{schema_name}\"'".format(
        name=name, schema_name=schema_name))
    shell(u"gosu postgres psql -c 'ALTER TABLE \"{schema_name}\".\"{name}\" "
          u"RENAME TO \"{dataset_name}\"'".format(
              schema_name=schema_name, name=name, dataset_name=dataset_name))


def build(url, s3_bucket, tmp_path): # pylint: disable=too-many-locals
    """
    Main function.  Takes the URL of the data.json spec.

    Writes the name of the dataset to file at `/name` when done.
    """
    if not os.path.exists(tmp_path):
        os.mkdir(tmp_path)

    resp = requests.get(url).json()

    dataset_name = resp[u'tableName']
    schema_name = resp.get(u'schemaName', u'contrib')
    current_digest = get_current_digest(resp)
    old_digest = get_old_digest(s3_bucket, u'/'.join([schema_name, dataset_name]))
    tmpname = u'tmp_{}'.format(tmp_path.split('.')[-1].lower())

    # Able to verify nothing has changed, abort.
    if current_digest and old_digest and current_digest == old_digest:
        LOGGER.info(u'Current digest %s and old digest %s match, skipping %s',
                    current_digest, old_digest, dataset_name)
        sys.exit(100)  # Error exit code to stop build.sh

    data_type = resp[u'data'][u'type']
    if data_type in (u'csv', u'shapefile'):
        shell("gosu postgres psql -c 'DROP TABLE IF EXISTS \"{}\".\"{}\"'".format(
            schema_name, dataset_name))

        for before in resp.get(u'before', []):
            run_remote_script(before, tmp_path, {'DATASET': 'data'})

        data_path = wget_download(resp[u'data'][u'@id'], 'data', tmp_path)

        if data_type == u'csv':
            schema = resp[u'schema']
            if 'postgres' in schema:
                schema_path = wget_download(schema[u'postgres'][u'@id'], 'schema.sql', tmp_path)
            else:
                schema_path = os.path.join(tmp_path, 'schema.sql')
                with open(schema_path, 'w') as schema_file:
                    schema_file.write(generate_schema(tmpname, schema))

            run_postgres_script(schema_path)

            pgload_import(tmpname, schema_name, dataset_name, data_path,
                          resp.get(u'load_format', {}), tmp_path)

        elif data_type == u'shapefile':
            shell(u'unzip {} -d {}'.format(data_path, tmp_path))
            ogr2ogr_import(schema_name, dataset_name, tmp_path)

        for after in resp.get(u'after', []):
            run_remote_script(after, tmp_path, {'DATASET': 'data'})
    else:
        LOGGER.warn(u'Not yet able to deal with data type %s', data_type)
        sys.exit(1)

    sys.stdout.write(current_digest)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3])
