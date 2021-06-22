# -*- title: bindCommerce / Esporta prodotti -*-
# -*- coding: utf-8 -*-
# -*- konga-version-min: 1.9.0 -*-
# -*- py3k-safe -*-
# -*- requires: requests -*-

import sys
import argparse
import shlex
import datetime
import io
import requests

from xml.etree import ElementTree as ET

import kongalib
import kongautil
import kongaui



def strip_html(html):
	from html.parser import HTMLParser
	class Stripper(HTMLParser):
		def __init__(self):
			HTMLParser.__init__(self)
			self.skip = 0
			self.fed = []
			self.feed(ensure_unicode(html))
		def handle_starttag(self, tag, attrs):
			if tag in ( 'head', 'script' ):
				self.skip += 1
			elif tag == 'br':
				self.fed.append('\n')
		def handle_endtag(self, tag):
			if tag in ( 'head', 'script' ):
				self.skip -= 1
			elif tag == 'p':
				self.fed.append('\n')
		def handle_startendtag(self, tag, attrs):
			if tag == 'br':
				self.fed.append('\n')
		def handle_data(self, d):
			if self.skip == 0:
				self.fed.append(d)
		def get_data(self):
			return ''.join(self.fed)
	return Stripper().get_data().strip()



def ensure_node(parent, name, attribs=None):
	for part in name.split('/'):
		node = parent.find(part)
		if node is None:
			node = ET.SubElement(parent, part, attribs or {})
		parent = node
	return node



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



def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--code-azienda', help="Codice azienda per cui esportare i prodotti")
	parser.add_argument('--code-titdep', help="Codice titolo di deposito")
	parser.add_argument('--images-url-prefix', help="Prefisso dell'URL delle immagini")
	args = shlex.split(' '.join(sys.argv[1:]))
	options = parser.parse_args(args)
	if options.code_azienda:
		params.update({
			'code_azienda': options.code_azienda,
			'code_titdep': options.code_titdep,
			'images_url_prefix': options.images_url_prefix,
		})
	else:
		params = kongaui.execute_form([
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
				'name': 'images_url_prefix',
				'label': "Prefisso dell'URL delle immagini",
			},
			],
			"Esporta prodotti",
			"Selezionare l'azienda da cui esportare i prodotti su bindCommerce.",
			condition = "code_azienda")
		if not params:
			return

	log = kongalib.Log()
	client = kongautil.connect()
	kongaui.open_progress('Esportazione prodotti in corso...')
	client.begin_transaction()
	datadict = client.get_data_dictionary()
	prod_type = datadict.get_choice('TipologieArticoli')
	binary_type = datadict.get_choice('Resources')
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

		ids = client.select_data('EB_Articoli', [ 'EB_Articoli.id' ], kongalib.AND(
				kongalib.OR(kongalib.OperandIsNull('EB_Articoli.ref_Azienda'), kongalib.OperandEQ('EB_Articoli.ref_Azienda.Codice', params['code_azienda'])),
				kongalib.OperandEQ('EB_Articoli.val_Tipo', prod_type.STANDARD)
		))
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
			kongaui.set_progress((index * 100.0) / len(ids), None, 'Articolo %d di %d' % (index+1, len(ids)))
			record = client.get_record('EB_Articoli', id=record_id, field_names=[
				'EB_Articoli.ref_Produttore.RagioneSociale',
				'EB_Articoli.ref_Fornitore.RagioneSociale',
				'EB_Articoli.ref_AliquotaIVA.PercentualeIVA',
			])
			prod = ET.SubElement(products, 'Product')
			for attrib, key in attribs_map.items():
				if record[key]:
					ensure_node(prod, attrib).text = record[key]
			ensure_node(prod, 'Language').text = 'IT'
			ensure_node(prod, 'BarcodeKind').text = 'EAN'
			ensure_node(prod, 'Prices/Price/ListCode').text = 'Public'
			ensure_node(prod, 'Prices/Price/Currency').text = 'EUR'

			if not prod.find('DescriptionHtml'):
				ensure_node(prod, 'DescriptionHtml').text = record['EB_Articoli.tra_Descrizione']
			if prod.find('Dimensions/Weight'):
				ensure_node(prod, 'Dimensions/WeightUom').text = 'Kg'
			if prod.find('Dimensions/Length') or prod.find('Dimensions/Width') or prod.find('Dimensions/Height'):
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
					tag_desc, tag_id = client.select_data('EB_Tags', ['EB_Tags.Descrizione', 'EB_Tags.ref_TagPadre' ], OperandEQ('EB_Tags.id', tag_id))[0]
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
					images.append(binary[1])
			if images:
				pictures = ensure_node(prod, 'Pictures')
				for image in images:
					pic = ET.SubElement(pictures, 'Picture')
					url = params['images_url_prefix']
					if not url.endswith('/'):
						url += '/'
					ET.SubElement(pic, 'URL').text = url + image

		xml = save_xml(root)
		print(str(xml, 'utf-8'))
	finally:
		client.rollback_transaction()
		kongaui.close_progress()



if __name__ == '__main__':
	main()
