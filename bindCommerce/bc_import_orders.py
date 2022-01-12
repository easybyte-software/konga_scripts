# -*- title: bindCommerce / Importa ordini -*-
# -*- coding: utf-8 -*-
# -*- konga-version-min: 1.9.0 -*-
# -*- py3k-safe -*-
# -*- requires: requests -*-

# Si assume che siano stati configurati i primi 4 riferimenti aggiuntivi di Ordini Clienti come segue:
#
# - EB_OrdiniClienti.RifAggiuntivo1: numero d'ordine interno a bindCommerce
# - EB_OrdiniClienti.RifAggiuntivo2: numero d'ordine del canale di vendita
# - EB_OrdiniClienti.RifAggiuntivo3: stato dell'ordine sul canale di vendita
# - EB_OrdiniClienti.RifAggiuntivo4: note inserite dal venditore
#



import sys
import os, os.path
import shlex
import datetime
import io
import configparser
import html
import requests

from pprint import pprint
from xml.etree import ElementTree as ET

import kongalib
import kongautil
import kongaui



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
		'name': 'code_tipo_doc',
		'label': "Codice tipologia documento",
		'table': 'EB_TipologieDocumenti',
		'type': 'code',
	},
	{
		'name': 'code_rounding_prod',
		'label': "Codice prodotto per arrotondamento",
		'table': 'EB_Articoli',
		'type': 'code',
	},
]



def prepare_record(node, map, code_azienda=None):
	record = {}
	for key, (ensure, *params) in map.items():
		params = [ (node.find(p).text or '').strip() for p in params ]
		# print(ensure, params)
		record[key] = ensure(*params)

	if code_azienda is not None:
		tablename = list(map.keys())[0].split('.')[0]
		record['%s.code_Azienda' % tablename] = code_azienda

	return record



def get_product_info(client, product_code):
	um = None
	vat = None
	result = client.select_data('EB_Articoli', ['EB_Articoli.ref_UnitaMisura', 'EB_Articoli.ref_AliquotaIVA.Codice'], kongalib.OperandEQ('EB_Articoli.Codice', product_code))
	if result:
		vat = result[0][1]
		result = client.select_data('EB_RigheUnitaMisura', ['EB_RigheUnitaMisura.Abbreviazione', 'EB_RigheUnitaMisura.val_UnitaMisFiscale', 'EB_RigheUnitaMisura.val_PreferitaVdt'], kongalib.OperandEQ('EB_RigheUnitaMisura.ref_UnitaMisura', result[0][0]))
		for abbr, fisc, default in result:
			if fisc:
				um = abbr
				break
			elif default:
				um = abbr
	return um, vat



def main():
	payment_code = {}
	vat_code = {}

	def ensure_date(ts):
		return datetime.datetime.strptime(ts[:10], '%Y-%m-%d').date()

	def ensure_name(name, surname, company):
		if company:
			return company
		else:
			return (' '.join([ surname, name ])).strip()

	def ensure_country(code):
		return val_nations[code or 'IT']

	def ensure_phone(phone, mobile):
		return ' - '.join([ p for p in [ phone, mobile ] if p ])

	def ensure_payment(name):
		return payment_code[name.lower()]

	def ensure_vat(rate):
		return vat_code[kongalib.Decimal(rate)]


	order_map = {
		'EB_OrdiniClienti.RiferimentoWeb':				( str, 'General/Number' ),
		'EB_OrdiniClienti.DataOrdine':					( ensure_date, 'General/Date' ),
		'EB_OrdiniClienti.RifAggiuntivo1':				( str, 'General/bindCommerceNumber' ),
		'EB_OrdiniClienti.RifAggiuntivo2':				( str, 'General/Number' ),
		'EB_OrdiniClienti.RifAggiuntivo3':				( str, 'General/StateName' ),
		'EB_OrdiniClienti.RagioneSociale':				( ensure_name, 'Customer/Name', 'Customer/Surname', 'Customer/Company' ),
		'EB_OrdiniClienti.Indirizzo':					( str, 'Customer/Address' ),
		'EB_OrdiniClienti.CAP':							( str, 'Customer/Postcode' ),
		'EB_OrdiniClienti.Localita':					( str, 'Customer/City' ),
		'EB_OrdiniClienti.Provincia':					( str, 'Customer/Province' ),
		'EB_OrdiniClienti.val_Nazione':					( ensure_country, 'Customer/CountryCode' ),
		'EB_OrdiniClienti.PartitaIVA':					( str, 'Customer/VatCode' ),
		'EB_OrdiniClienti.CodiceFiscale':				( str, 'Customer/FiscalCode' ),
		'EB_OrdiniClienti.Telefono':					( ensure_phone, 'Customer/Phone', 'Customer/MobPhone' ),
		'EB_OrdiniClienti.Email':						( str, 'Customer/Email' ),
		'EB_OrdiniClienti.CodUnivocoUfficio':			( str, 'Customer/EInvoiceDestCode' ),
		'EB_OrdiniClienti.RagSoc_Dest':					( ensure_name, 'Delivery/Name', 'Delivery/Surname', 'Delivery/Company' ),
		'EB_OrdiniClienti.Indirizzo_Dest':				( str, 'Delivery/Address' ),
		'EB_OrdiniClienti.CAP_Dest':					( str, 'Delivery/Postcode' ),
		'EB_OrdiniClienti.Localita_Dest':				( str, 'Delivery/City' ),
		'EB_OrdiniClienti.Provincia_Dest':				( str, 'Delivery/Province' ),
		'EB_OrdiniClienti.val_NazioneDest':				( ensure_country, 'Delivery/CountryCode' ),
		'EB_OrdiniClienti.code_CondizionePagamento':	( ensure_payment, 'Payments/PaymentName' ),
		'EB_OrdiniClienti.code_Valuta':					( str, 'Amounts/Currency' ),
		'EB_OrdiniClienti.Note':						( str, 'Amounts/InternalComment' ),
		'EB_OrdiniClienti.RifAggiuntivo4':				( str, 'Amounts/SellerNote' ),
		'EB_OrdiniClienti.SpeseTrasporto':				( kongalib.Decimal, 'Amounts/ShippingCostWithoutTax' ),
	}

	customer_map = {
		'EB_ClientiFornitori.CodiceAlternativo':		( str, 'Customer/Code' ),
		'EB_ClientiFornitori.RagioneSociale':			( ensure_name, 'Customer/Name', 'Customer/Surname', 'Customer/Company' ),
		'EB_ClientiFornitori.Indirizzo':				( str, 'Customer/Address' ),
		'EB_ClientiFornitori.CAP':						( str, 'Customer/Postcode' ),
		'EB_ClientiFornitori.Localita':					( str, 'Customer/City' ),
		'EB_ClientiFornitori.Provincia':				( str, 'Customer/Province' ),
		'EB_ClientiFornitori.val_Nazione':				( ensure_country, 'Customer/CountryCode' ),
		'EB_ClientiFornitori.PartitaIVA':				( str, 'Customer/VatCode' ),
		'EB_ClientiFornitori.CodiceFiscale':			( str, 'Customer/FiscalCode' ),
		'EB_ClientiFornitori.Telefono':					( ensure_phone, 'Customer/Phone', 'Customer/MobPhone' ),
		'EB_ClientiFornitori.IndirizzoEmail':			( str, 'Customer/Email' ),
		'EB_ClientiFornitori.IndirizzoPEC':				( str, 'Customer/Pec' ),
		'EB_ClientiFornitori.IndirizzoPECFE':			( str, 'Customer/Pec' ),
		'EB_ClientiFornitori.CodUnivocoUfficio':		( str, 'Customer/EInvoiceDestCode' ),
		'EB_ClientiFornitori.code_Valuta':				( str, 'Amounts/Currency' ),
	}

	dest_map = {
		'EB_Indirizzi.RagioneSociale':					( ensure_name, 'Delivery/Name', 'Delivery/Surname', 'Delivery/Company' ),
		'EB_Indirizzi.Indirizzo':						( str, 'Delivery/Address' ),
		'EB_Indirizzi.CAP':								( str, 'Delivery/Postcode' ),
		'EB_Indirizzi.Localita':						( str, 'Delivery/City' ),
		'EB_Indirizzi.Provincia':						( str, 'Delivery/Province' ),
		'EB_Indirizzi.val_Nazione':						( ensure_country, 'Delivery/CountryCode' ),
		'EB_Indirizzi.Telefono':						( ensure_phone, 'Delivery/Phone', 'Delivery/MobPhone' ),
		'EB_Indirizzi.Email':							( str, 'Delivery/Email' ),
	}

	row_map = {
		'EB_RigheOrdiniClienti.code_Articolo':			( str, 'Code' ),
		'EB_RigheOrdiniClienti.DescArticolo':			( str, 'Description' ),
		'EB_RigheOrdiniClienti.Quantita':				( kongalib.Decimal, 'Qty' ),
		'EB_RigheOrdiniClienti.QtaFiscale':				( kongalib.Decimal, 'Qty' ),
		'EB_RigheOrdiniClienti.ValoreUnitario':			( kongalib.Decimal, 'PriceVatExcluded' ),
		'EB_RigheOrdiniClienti.ValoreUnitIVAInclusa':	( kongalib.Decimal, 'Price' ),
		'EB_RigheOrdiniClienti.Sconto':					( kongalib.Decimal, 'Discounts' ),
		'EB_RigheOrdiniClienti.code_AliquotaIVA':		( ensure_vat, 'VatRate' ),
	}


	config_file = os.path.splitext(sys.argv[0])[0] + '.cfg'

	config = configparser.RawConfigParser({ param['name']: '' for param in PARAMS })
	config.add_section('kongautil.connect')
	config.add_section('kongautil.print_layout')
	config.add_section('bindCommerce')
	config.read(config_file)

	if kongautil.is_batch():
		params = { param['name']: config.get('bindCommerce', param['name']) for param in PARAMS }
	else:
		for param in PARAMS:
			param['default'] = config.get('bindCommerce', param['name'])
		params = kongaui.execute_form(PARAMS,
			"Importa ordini",
			condition = "url and token and code_azienda and code_titdep")
		if not params:
			return

	for index in range(1, 11):
		try:
			name = config.get('bindCommerce', 'payment_name_%d' % index)
			code = config.get('bindCommerce', 'payment_code_%d' % index)
			if (not name) or (not code):
				continue
		except:
			break
		else:
			payment_code[name.lower()] = code

	for index in range(1, 11):
		try:
			perc = config.get('bindCommerce', 'vat_perc_%d' % index)
			code = config.get('bindCommerce', 'vat_code_%d' % index)
			if (not perc) or (not code):
				continue
		except:
			break
		else:
			vat_code[kongalib.Decimal(perc)] = code

	log = kongalib.Log()
	client = kongautil.connect(config=config_file)
	if not kongautil.is_batch():
		kongaui.open_progress('Importazione ordini in corso...')
	client.begin_transaction()
	datadict = client.get_data_dictionary()
	val_nations = {}
	nations = datadict.get_choice('Nazioni')
	for key in nations.keys():
		val_nations[key[:2]] = getattr(nations, key)
	dest_types = datadict.get_choice('TipiIndirizzo')
	code_azienda = params['code_azienda']
	try:
		result = client.select_data('EB_TitoliDeposito', ['EB_TitoliDeposito.id', 'EB_TitoliDeposito.ref_Magazzino'], kongalib.AND(kongalib.OperandEQ('EB_TitoliDeposito.Codice', params['code_titdep']), kongalib.OperandEQ('EB_TitoliDeposito.ref_Magazzino.ref_Azienda.Codice', code_azienda)))
		if not result:
			raise RuntimeError("Titolo di deposito non trovato per l'azienda specificata")
		id_titdep, id_mag = result[0]
		id_caus_mag = client.select_data('EB_TipologieDocumenti', ['EB_TipologieDocumenti.ref_CausaleMagazzino'], kongalib.OperandEQ('EB_TipologieDocumenti.Codice', params['code_tipo_doc']))[0][0]

		response = requests.get(params['url'], headers={
			'cache-control': 'no-cache',
			'token': params['token'],
		})
		response.raise_for_status()
		if response.text:
			file = io.BytesIO(response.text.encode('utf-8'))
			root = ET.ElementTree().parse(file)

			# ET.indent(root)
			# with open('orders.xml', 'w', encoding='utf-8') as f:
			# 	f.write(ET.tostring(root, encoding='unicode'))
			# print(ET.tostring(root, encoding='unicode'))

			for document in root.findall('Document'):
				customer = prepare_record(document, customer_map, code_azienda)
				dest = prepare_record(document, dest_map, code_azienda)
				order = prepare_record(document, order_map, code_azienda)

				result = client.select_data('EB_ClientiFornitori', ['EB_ClientiFornitori.Codice'], kongalib.OperandEQ('EB_ClientiFornitori.CodiceAlternativo', customer['EB_ClientiFornitori.CodiceAlternativo']))
				if result:
					customer_code = result[0][0]
				else:
					customer['EB_ClientiFornitori.Codice'] = customer['EB_ClientiFornitori.CodiceAlternativo']
					customer['EB_ClientiFornitori.Tipo'] = 1
					customer_code = client.insert_record('EB_ClientiFornitori', customer, code_azienda)[1]
				order['EB_OrdiniClienti.code_Cliente'] = customer_code

				result = client.select_data('EB_Indirizzi', ['EB_Indirizzi.Codice'], kongalib.AND(kongalib.OperandEQ('EB_Indirizzi.RagioneSociale', dest['EB_Indirizzi.RagioneSociale']), kongalib.OperandEQ('EB_Indirizzi.Indirizzo', dest['EB_Indirizzi.Indirizzo'])))
				if result:
					dest_code = result[0][0]
				else:
					dest['EB_Indirizzi.code_ClienteFornitore'] = customer_code
					dest['EB_Indirizzi.val_TipoIndirizzo'] = dest_types.DEST_MERCE
					dest_code = client.insert_record('EB_Indirizzi', dest, code_azienda)[1]
				order['EB_OrdiniClienti.code_Indirizzo'] = dest_code

				order['@rows'] = []
				for row in document.findall('Rows/Row'):
					rowdata = prepare_record(row, row_map)
					rowdata['EB_RigheOrdiniClienti.code_RigheUnitaMisura'] = get_product_info(client, rowdata['EB_RigheOrdiniClienti.code_Articolo'])[0]
					order['@rows'].append(rowdata)
				order['EB_OrdiniClienti.code_Tipologia'] = params['code_tipo_doc']
				order['EB_OrdiniClienti.ref_CausaleMagazzino'] = id_caus_mag
				order['EB_OrdiniClienti.ref_TitDepUscita'] = id_titdep

				result = client.select_data('EB_OrdiniClienti', ['EB_OrdiniClienti.id'], kongalib.OperandEQ('EB_OrdiniClienti.RifAggiuntivo1', order['EB_OrdiniClienti.RifAggiuntivo1']))
				if not result:
					order_id = client.insert_record('EB_OrdiniClienti', order, code_azienda)[0]
					order = client.get_record('EB_OrdiniClienti', id=order_id)
					total = kongalib.Decimal(document.find('Amounts/Total').text or '0')
					diff = total - order['TotaleDocumento']
					if diff:
						um, vat = get_product_info(client, params['code_rounding_prod'])
						order['@rows'].append({
							'EB_RigheOrdiniClienti.code_Articolo': params['code_rounding_prod'],
							'EB_RigheOrdiniClienti.DescArticolo': 'Arrotondamento',
							'EB_RigheOrdiniClienti.Quantita': 1,
							'EB_RigheOrdiniClienti.code_RigheUnitaMisura': um,
							'EB_RigheOrdiniClienti.ValoreUnitario': diff,
							'EB_RigheOrdiniClienti.ValoreUnitIVAInclusa': diff,
							'EB_RigheOrdiniClienti.code_AliquotaIVA': vat,
						})
						client.update_record('EB_OrdiniClienti', id=order_id, data=order)

	except:
		client.rollback_transaction()
		raise
	else:
		client.commit_transaction()
	finally:
		if not kongautil.is_batch():
			kongaui.close_progress()



if __name__ == '__main__':
	main()
