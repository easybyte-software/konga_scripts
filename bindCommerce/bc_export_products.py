# -*- title: bindCommerce / Esporta prodotti -*-
# -*- coding: utf-8 -*-
# -*- konga-version-min: 1.9.0 -*-
# -*- py3k-safe -*-
# -*- requires: requests -*-

import sys
import os, os.path
import argparse
import shlex
import logging
import logging.handlers
import datetime
import io
import configparser
import html
import urllib
import urllib.parse
import ftplib
import requests

from xml.etree import ElementTree as ET

import kongalib
import kongautil
import kongaui


BASE_NAME = os.path.splitext(sys.argv[0])[0]

PARAMS = [
	{
		'name': 'url',
		'label': "URL del connettore bindCommerce",
		'size': 350,
	},
	{
		'name': 'token',
		'label': "Token di accesso bindCommerce",
		'type': 'password',
	},
	{
		'name': 'code_azienda',
		'label': "Codice azienda",
		'type': 'company_code',
	},
	{
		'name': 'code_titdep',
		'label': "Codice titolo di deposito",
		'table': 'EB_TitoliDeposito',
		'type': 'code',
	},
	{
		'name': 'code_from',
		'label': "Da codice",
		'table': 'EB_Articoli',
		'type': 'code',
	},
	{
		'name': 'code_to',
		'label': "A codice",
		'table': 'EB_Articoli',
		'type': 'code',
	},
	{
		'name': 'ecomm_only',
		'label': "Solo articoli con gestione e-business",
		'type': 'bool',
		'default': True,
	},
	{
		'name': 'last_days',
		'label': "Solo articoli modificati",
		'type': 'choice',
		'items': [ 'no (invia tutti)', 'negli ultimi 3 giorni', 'negli ultimi 7 giorni', 'negli ultimi 15 giorni' ],
		'default': 0,
	},
	{
		'name': 'images_url_prefix',
		'label': "Prefisso dell'URL delle immagini",
		'size': 350,
	},
	{
		'name': 'images_ftp_host',
		'label': "Host ftp per l'upload delle immagini",
		'size': 350,
	},
	{
		'name': 'images_ftp_username',
		'label': "Nome utente ftp per l'upload delle immagini",
	},
	{
		'name': 'images_ftp_password',
		'label': "Password ftp per l'upload delle immagini",
		'type': 'password',
	},
	{
		'name': 'images_ftp_root',
		'label': "Percorso sull'ftp dove eseguire l'upload delle immagini",
		'size': 350,
	},
]



def ensure_node(parent, name, attribs=None):
	for part in name.split('/'):
		node = parent.find(part)
		if node is None:
			node = ET.SubElement(parent, part, attribs or {})
		parent = node
	return node



def escape(text):
	if not isinstance(text, str):
		text = str(text)
	text = html.escape(text).encode('ascii', 'xmlcharrefreplace')
	return str(text, 'utf-8')



def save_xml(source):
	def indent_xml(elem, level=0, spacer='  '):
		i = "\n" + (level * spacer)
		if len(elem):
			if not elem.text or not elem.text.strip():
				elem.text = i + "  "
			if not elem.tail or not elem.tail.strip():
				elem.tail = i
			for elem in elem:
				indent_xml(elem, level + 1)
			if not elem.tail or not elem.tail.strip():
				elem.tail = i
		else:
			if level and (not elem.tail or not elem.tail.strip()):
				elem.tail = i

	indent_xml(source)
	document = ET.ElementTree(source)
	file = io.BytesIO()
	file.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
	document.write(file, encoding='utf-8')
	return file.getvalue()



def setup_logging(logfile):
	logger = logging.getLogger()
	formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
	try:
		handler = logging.handlers.RotatingFileHandler(logfile, maxBytes=1000000, backupCount=10)
	except:
		print("Unable to save log files in %s, falling back to stdout" % logfile)
		handler = logging.StreamHandler()
	handler.setLevel(logging.DEBUG)
	handler.setFormatter(formatter)
	logger.addHandler(handler)
	logger.setLevel(logging.INFO)

	class Handler(logging.StreamHandler):
		def __init__(self, formatter):
			super().__init__(logging.DEBUG)
			self._log = kongalib.Log()
			self.setFormatter(formatter)
		def get_log(self):
			return self._log
		def emit(self, record):
			msg = self.format(record)
			func = {
				logging.WARNING: self._log.warning,
				logging.ERROR: self._log.error,
				logging.CRITICAL: self._log.error,
			}.get(record.levelno, self._log.info)
			func(msg)
	handler = Handler(formatter)
	logger.addHandler(handler)

	return handler.get_log()



def main():
	parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]))
	parser.add_argument('--dry-run', action='store_true', help="Tenta le operazioni desiderate ma non applica alcuna modifica")
	parser.add_argument('-q', '--quiet', action='store_true', help='Non mostrare alcun output a video')

	args = shlex.split(' '.join(sys.argv[1:]))
	options = parser.parse_args(args)

	logfile = BASE_NAME + '.log'
	log = setup_logging(logfile)

	config_file = BASE_NAME + '.cfg'

	config = configparser.RawConfigParser({})
	config.add_section('kongautil.connect')
	config.add_section('kongautil.print_layout')
	config.add_section('bindCommerce')
	config.read(config_file)

	if kongautil.is_batch():
		params = { param['name']: config.get('bindCommerce', param['name'], fallback=param.get('default', '')) for param in PARAMS }
		params['last_days'] = { '3': 1, '7': 2, '15': 3 }.get(params['last_days'], 0)
	else:
		for param in PARAMS:
			param['default'] = config.get('bindCommerce', param['name'], fallback=param.get('default', ''))
			if param['name'] == 'last_days':
				param['default'] = { '3': 1, '7': 2, '15': 3 }.get(param['default'], 0)
		params = kongaui.execute_form(PARAMS,
			"Esporta prodotti",
			condition = "url and token and code_azienda and code_titdep")
		if not params:
			return

	if params['images_ftp_host']:
		ftp = ftplib.FTP_TLS(params['images_ftp_host'])
		ftp.login(params['images_ftp_username'], params['images_ftp_password'])
		ftp.prot_p()
		ftp.cwd(params['images_ftp_root'] or '/')
	else:
		ftp = None
	client = kongautil.connect(config=config_file)
	logging.info('Inizio esportazione prodotti')
	if not options.quiet:
		kongaui.open_progress('Esportazione prodotti in corso...')
	client.begin_transaction()
	datadict = client.get_data_dictionary()
	prod_type = datadict.get_choice('TipologieArticoli')
	binary_type = datadict.get_choice('Resources')
	yesno_type = datadict.get_choice('YesNo')
	try:
		today = datetime.datetime.now().date().isoformat()
		result = client.select_data('EB_Esercizi', ['EB_Esercizi.id'], kongalib.AND(kongalib.OperandLE('EB_Esercizi.DataInizio', today), kongalib.OperandGE('EB_Esercizi.DataFine', today)), kongalib.OperandEQ('EB_Esercizi.ref_Azienda.Codice', params['code_azienda']))
		if not result:
			raise RuntimeError('Nessun esercizio corrispondente alla data odierna')
		id_esercizio = result[0][0]

		result = client.select_data('EB_TitoliDeposito', ['EB_TitoliDeposito.id', 'EB_TitoliDeposito.ref_Magazzino'], kongalib.AND(kongalib.OperandEQ('EB_TitoliDeposito.Codice', params['code_titdep']), kongalib.OperandEQ('EB_TitoliDeposito.ref_Magazzino.ref_Azienda.Codice', params['code_azienda'])))
		if not result:
			raise RuntimeError("Titolo di deposito non trovato per l'azienda specificata")
		id_titdep, id_mag = result[0]

		w_ex = [
			kongalib.OR(kongalib.OperandIsNull('EB_Articoli.ref_Azienda'), kongalib.OperandEQ('EB_Articoli.ref_Azienda.Codice', params['code_azienda'])),
			kongalib.OperandEQ('EB_Articoli.val_Tipo', prod_type.STANDARD),
		]
		if params['code_from']:
			w_ex.append(kongalib.OperandGE('EB_Articoli.Codice', params['code_from']))
		if params['code_to']:
			w_ex.append(kongalib.OperandLE('EB_Articoli.Codice', params['code_to']))
		if params['ecomm_only']:
			w_ex.append(kongalib.OperandEQ('EB_Articoli.val_GestioneWeb', yesno_type.YES))
		if params['last_days']:
			limit = datetime.datetime.combine(datetime.date.today(), datetime.time(23, 59, 59, 9999)) - datetime.timedelta(days={ 1: 3, 2: 7, 3: 15 }[params['last_days']])
			w_ex.append(kongalib.OperandGE('EB_Articoli.TSModifica', limit.isoformat(' ')))

		ids = client.select_data('EB_Articoli', [ 'EB_Articoli.id' ], kongalib.AND(*w_ex), 'EB_Articoli.Codice')
		attribs_map = {
			'Code':						'EB_Articoli.Codice',
			'Barcode':					'EB_Articoli.BarCode',
			'Title':					'EB_Articoli.tra_Descrizione',
			'DescriptionHtml':			'EB_Articoli.tra_DescrizioneEstesa',
			'ShortDescription':			'EB_Articoli.tra_DescrizioneScontrino',
			# 'Notes':					'@notes',
			'Manufacturer':				'EB_Articoli.ref_Produttore.RagioneSociale',
			'MPN':						'EB_Articoli.CodiceArticoloFornitore',
			'Supplier':					'EB_Articoli.ref_Fornitore.RagioneSociale',
			'Dimensions/Weight':		'EB_Articoli.Peso',
			'Dimensions/Length':		'EB_Articoli.Profondita',
			'Dimensions/Width':			'EB_Articoli.Larghezza',
			'Dimensions/Height':		'EB_Articoli.Altezza',
		}
		root = ET.Element('bindCommerceProducts', { 'Mode': 'full' })
		products = ET.SubElement(root, 'Products')
		for index, record_id in enumerate(ids):
			record_id = record_id[0]
			if not options.quiet:
				kongaui.set_progress((index * 100.0) / len(ids), None, 'Articolo %d di %d' % (index+1, len(ids)))
				if kongaui.is_progress_aborted():
					return
			record = client.get_record('EB_Articoli', id=record_id, field_names=[
				'EB_Articoli.ref_Produttore.RagioneSociale',
				'EB_Articoli.ref_Fornitore.RagioneSociale',
				'EB_Articoli.ref_AliquotaIVA.PercentualeIVA',
			])
			logging.info('Esporto articolo %s' % record['EB_Articoli.Codice'])
			prod = ET.SubElement(products, 'Product')
			for attrib, key in attribs_map.items():
				if record[key]:
					ensure_node(prod, attrib).text = escape(record[key])
			ensure_node(prod, 'Language').text = 'IT'
			ensure_node(prod, 'BarcodeKind').text = 'EAN'
			ensure_node(prod, 'Prices/Price/ListCode').text = 'Public'
			ensure_node(prod, 'Prices/Price/Currency').text = 'EUR'

			if prod.find('DescriptionHtml') is None:
				ensure_node(prod, 'DescriptionHtml').text = escape(record['EB_Articoli.tra_Descrizione'])
			if prod.find('Dimensions/Weight') is not None:
				ensure_node(prod, 'Dimensions/WeightUom').text = 'Kg'
			if (prod.find('Dimensions/Length') is not None) or (prod.find('Dimensions/Width') is not None) or (prod.find('Dimensions/Height') is not None):
				ensure_node(prod, 'Dimensions/LwhUom').text = 'cm'
			categories = []
			id_cat = record['EB_Articoli.ref_CategoriaMerceologica']
			while id_cat:
				result = client.select_data('EB_CategorieMerceologiche', ['EB_CategorieMerceologiche.tra_Descrizione', 'EB_CategorieMerceologiche.ref_GruppoCategorie'], kongalib.OperandEQ('EB_CategorieMerceologiche.id', id_cat))
				if result:
					categories.append(result[0][0])
					id_cat = result[0][1]
				else:
					break
			if categories:
				ensure_node(prod, 'Categories/Category').text = '|'.join(categories[::-1])
			result = client.select_data('EB_ProgressiviArticoli', [ 'EB_ProgressiviArticoli.id' ], kongalib.AND(kongalib.OperandEQ('EB_ProgressiviArticoli.ref_Articolo', record_id), kongalib.OperandEQ('EB_ProgressiviArticoli.ref_Magazzino', id_mag), kongalib.OperandEQ('EB_ProgressiviArticoli.ref_Esercizio', id_esercizio)))
			if result:
				result = client.select_data('EB_GiacenzeTitDep', [ 'EB_GiacenzeTitDep.Giacenza' ], kongalib.AND(kongalib.OperandEQ('EB_GiacenzeTitDep.ref_ProgressivoArticolo', result[0][0]), kongalib.OperandEQ('EB_GiacenzeTitDep.ref_TitoloDeposito', id_titdep)))
			if result:
				qta = result[0][0] or 0
			else:
				qta = 0
			ensure_node(prod, 'Qty').text = str(qta)

			result = client.select_data('EB_TagsArticoli', [ 'EB_TagsArticoli.ref_Tag' ], kongalib.OperandEQ('EB_TagsArticoli.ref_Articolo', record_id))
			attributes = ensure_node(prod, 'Attributes')
			for id_tag in result:
				id_tag = id_tag[0]
				tag = []
				while id_tag:
					tag_desc, id_tag = client.select_data('EB_Tags', ['EB_Tags.Descrizione', 'EB_Tags.ref_TagPadre' ], kongalib.OperandEQ('EB_Tags.id', id_tag))[0]
					tag.insert(0, tag_desc)
				node = ET.SubElement(attributes, 'Attribute', { 'lang': 'it' })
				if len(tag) > 1:
					ensure_node(node, 'Name').text = ' :: '.join(tag[:-1])
					ensure_node(node, 'Value').text = tag[-1]
				else:
					ensure_node(node, 'Name').text = tag[0]
					ensure_node(node, 'Value').text = ''

			ensure_node(prod, 'Prices/Price/Vat').text = str(kongalib.Decimal(record.get('EB_Articoli.ref_AliquotaIVA.PercentualeIVA') or 0) / 100.0)
			ensure_node(prod, 'Prices/Price/NetPrice').text = str(kongalib.Decimal(record['EB_Articoli.PrezzoVendita']))
			ensure_node(prod, 'Prices/Price/GrossPrice').text = str(kongalib.Decimal(record['EB_Articoli.PrezzoIVAInclusa']))
			ensure_node(prod, 'Prices/Price/OverridePrice').text = '0'
			ensure_node(prod, 'Prices/Price/Override').text = '0'

			binaries = client.list_binaries('EB_Articoli', record_id)
			images = []
			for binary in binaries:
				if binary[0] == binary_type.IMMAGINE_WEB:
					images.append((binary[1], binary[2]))
			if images:
				pictures = ensure_node(prod, 'Pictures')
				for image, filename in images:
					pic = ET.SubElement(pictures, 'Picture')
					url = params['images_url_prefix']
					if not url.endswith('/'):
						url += '/'
					ext = os.path.splitext(filename)[-1]
					if '.' in image:
						filename = os.path.splitext(image)[0]
					else:
						filename = image
					filename = urllib.parse.quote(os.path.basename(filename)) + ext
					ET.SubElement(pic, 'URL').text = url + filename
					if ftp is not None:
						data = client.fetch_binary('EB_Articoli', record_id, binary_type.IMMAGINE_WEB, image)[0]
						logging.info("Pubblico l'immagine '%s' su FTP" % filename)
						if not options.dry_run:
							try:
								ftp.storbinary('STOR %s' % filename, io.BytesIO(data))
							except Exception as e:
								logging.error('Errore di pubblicazione su FTP: %s' % str(e))

		xml = str(save_xml(root), 'utf-8')
		# print(xml)
		if not options.dry_run:
			logging.info('Pubblicazione degli articoli aggiornati su bindCommerce')
			response = requests.post(params['url'], headers={
				'cache-control': 'no-cache',
				'content-type': 'text/xml',
				'token': params['token'],
			}, data=xml)
			try:
				response.raise_for_status()
			except Exception as e:
				logging.error('Errore di pubblicazione articoli su bindCommerce: %s' % str(e))

	finally:
		client.rollback_transaction()
		if not options.quiet:
			kongaui.close_progress()
		logging.info('Termine esportazione prodotti')
	
	if not options.quiet:
		kongautil.print_log(log)


if __name__ == '__main__':
	main()
