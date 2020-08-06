# -*- title: Utilità / Riposiziona immagini e allegati -*-
# -*- coding: utf-8 -*-
# -*- py3k-safe -*-

from __future__ import print_function

import re
import os
import os.path
import uuid
import shutil
import tempfile

import kongalib
import kongautil
import kongaui



TIPO_ALLEGATO		= 0
TIPO_IMG_NORMALE	= 1
TIPO_IMG_WEB		= 2
TIPO_IMG_MINIATURA	= 3


FORM_FIELDS = [
	{
		'name': 'code_azienda',
		'label': "Codice azienda",
		'default': kongautil.get_window_vars().get('COMPANY_CODE', ''),
	},
	{
		'name': 'rename',
		'label': "Consolida nomi file",
		'tip': "Rinomina i file in modo da essere nella forma [CODE]_[UUID]",
		'type': 'bool',
		'default': False,
	},
	{
		'name': 'delete',
		'label': "Elimina riferimenti non validi",
		'tip': "Elimina i riferimenti ai file non trovati",
		'type': 'bool',
		'default': False,
	},
	{
		'name': 'simulate',
		'label': "Esegui simulazione",
		'tip': "Simula tutte le operazioni ma non apportare modifiche",
		'type': 'bool',
		'default': True,
	}
]



def reposition_entry(client, entry, fs_images, fs_data, tables, log, restore, code_azienda, id_azienda, rename, delete, simulate):
	old_filename = os.path.basename(entry['EB_DatiBinari.NomeAllegato'])
	table_name = tables[entry['EB_DatiBinari.ref_Tabella']]
	info = client.get_data_dictionary().get_field_info('%s.id' % table_name)
	if 'codes' in info:
		data = {}
		tipo = entry['EB_DatiBinari.val_Tipo']
		if rename:
			code = client.select_data(table_name, ['%s.%s' % (table_name, info['codes']) ], kongalib.OperandEQ('%s.id' % table_name, entry['EB_DatiBinari.Riga']))[0][0]
			code = str(code).zfill(8)
			suffix = str(uuid.uuid5(uuid.uuid1(),'mga')) + os.path.splitext(old_filename)[1]
			if tipo in ( TIPO_ALLEGATO, TIPO_IMG_NORMALE ):
				new_filename = '%s_%s'
			elif tipo == TIPO_IMG_WEB:
				new_filename = '%s_web_%s'
			elif tipo == TIPO_IMG_MINIATURA:
				new_filename = '%s_tmb_%s'
			new_filename = new_filename % (code, suffix)
			data['EB_DatiBinari.NomeAllegato'] = new_filename
		else:
			new_filename = old_filename
		if (table_name in ('EB_DocumentiFiscali', 'EB_OrdiniClienti', 'EB_OrdiniFornitori', 'EB_CaricoScarico')) and (entry.get('EB_DatiBinari.ref_Azienda', None) is None):
			data['EB_DatiBinari.ref_Azienda'] = id_azienda
		if data:
			entry.update(data)
			client.update_record('EB_DatiBinari', data, id=entry['EB_DatiBinari.id'])
		# log.info('Record ID %d: rinominato file da "%s" a "%s"' % (entry['EB_DatiBinari.id'], old_filename, new_filename))

		try:
			if (tipo != TIPO_ALLEGATO) and fs_images:
				external_path = kongautil.get_external_images_path(table_name, None if (entry.get('EB_DatiBinari.ref_Azienda', None) is None) else code_azienda)
				if external_path is None:
					log.error('Percorso delle immagini non accessibile; controllare la configurazione del database')
			elif (tipo == TIPO_ALLEGATO) and fs_data:
				external_path = kongautil.get_external_attachments_path(table_name, None if (entry.get('EB_DatiBinari.ref_Azienda', None) is None) else code_azienda)
				if external_path is None:
					log.error('Percorso degli allegati non accessibile; controllare la configurazione del database')
			else:
				external_path = None
		except RuntimeError as e:
			log.info('Potenziale errore sui dati binari: table_name = %s, EB_DatiBinari.Riga = %d, EB_DatiBinari.id = %d, EB_DatiBinari.ref_Azienda = %s' % (table_name, entry['EB_DatiBinari.Riga'], entry['EB_DatiBinari.id'], str(entry.get('EB_DatiBinari.ref_Azienda', None))))
			raise

		if external_path is not None:
			parts = os.path.basename(old_filename).split('_')
			if len(parts) == 1:
				old_subdir = '0'
			else:
				old_subdir = parts[0][:-3] or '0'
			new_subdir = new_filename[:-3] or '0'
			source = os.path.join(external_path, old_subdir, old_filename)
			if not os.path.exists(source):
				source = os.path.join(external_path, old_filename)
			dest = os.path.join(external_path, new_subdir, new_filename)
			dest_dir = os.path.dirname(dest)
			if (not os.path.exists(dest_dir)) and (not simulate):
				os.makedirs(dest_dir)
				os.chmod(dest_dir, 0o2777)
			if (source != dest) and os.path.exists(source):
				try:
					if not simulate:
						shutil.move(source, dest)
						restore.append((source, dest))
					log.info('Spostato file: "%s" -> "%s"' % (source, dest))
				except Exception as e:
					log.error(str(e))
					print("ERROR: while moving", source, '->', dest, ':', str(e))
			if not os.path.exists(source):
				if delete:
					client.delete_record('EB_DatiBinari', id=entry['EB_DatiBinari.id'])
					log.warning('File sorgente "%s" non esiste, cancello il record corrispondente dai dati binari (entry = %s)' % (source, repr(entry)))
				else:
					log.warning('File sorgente "%s" non esiste, lo salto (entry = %s)' % (source, repr(entry)))
					print("WARNING: file", source, "does not exist")




def main():
	params = kongaui.execute_form(FORM_FIELDS,
			"Riposizione immagini e allegati",
			"Questo script consolida la struttura delle directory dove vengono salvati immagini e allegati del database; in particolare, verrà creata una struttura gerarchica con sotto-directory, dentro cui ognuna verrà posizionato un massimo di 1000 file.<br/><br/>Sarà possibile inoltre consolidare anche i nomi dei file in modo da includere il codice del record corrispondente seguito da un UUID. Se richiesto, i riferimenti a file non esistenti verranno eliminati.<br/><br/>E' possibile eseguire una simulazione preventiva delle operazioni, che non ha alcun effetto su database e/o filesystem; alla fine verrà mostrato un log riepilogativo con il risultato di tutte le operazioni eseguite o simulate.<br/><br/>",
			condition = "code_azienda")
	if not params:
		return
	log = kongalib.Log()
	client = kongautil.connect()
	restore = []
	kongaui.open_progress('Riposizionamento allegati in corso...')
	client.begin_transaction()
	try:
		id_azienda = client.select_data('EB_Aziende', ['EB_Aziende.id'], OperandEQ('EB_Aziende.Codice', params['code_azienda']))[0][0]
		fs_images = (client.select_data('EB_Master', ['EB_Master.val_ImagesStorageType'])[0][0] == 0)
		fs_data = (client.select_data('EB_Master', ['EB_Master.val_AttachmentsStorageType'])[0][0] == 0)
		results = client.select_data('EB_Tabelle', ['EB_Tabelle.id', 'EB_Tabelle.Nome'])
		tables = { int(entry[0]): entry[1] for entry in results }
		results = client.select_data_as_dict('EB_DatiBinari', ['EB_DatiBinari.id', 'EB_DatiBinari.Riga', 'EB_DatiBinari.val_Tipo', 'EB_DatiBinari.NomeAllegato', 'EB_DatiBinari.ref_Azienda', 'EB_DatiBinari.ref_Tabella'], "(EB_DatiBinari.ref_Azienda IS NULL) OR (EB_DatiBinari.ref_Azienda.Codice = '%s')" % params['code_azienda'])
		for index, entry in enumerate(results):
			kongaui.set_progress((index * 100.0) / len(results), None, 'Allegato %d di %d' % (index+1, len(results)))
			if kongaui.is_progress_aborted():
				break
			reposition_entry(client, entry, fs_images, fs_data, tables, log, restore, params['code_azienda'], id_azienda, params['rename'], params['delete'], params['simulate'])
	finally:
		def do_restore():
			for dest, source in restore:
				try:
					shutil.move(source, dest)
				except:
					pass
		if kongaui.is_progress_aborted():
			client.rollback_transaction()
			do_restore()
			kongaui.close_progress()
		else:
			if log.has_errors() or params['simulate']:
				client.rollback_transaction()
				do_restore()
			else:
				client.commit_transaction()
			kongaui.close_progress()
			kongautil.print_log(log, "Esito %sriposizionamento allegati" % ('simulazione ' if params['simulate'] else ''))



main()

