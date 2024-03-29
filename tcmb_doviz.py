import pandas as pd

import pyodbc

from datetime import datetime, timedelta

import requests

from bs4 import BeautifulSoup

from sqlalchemy import create_engine

import logging



# Set up logging configuration

logging.basicConfig(filename='exchange_rates.log', level=logging.INFO,

                    format='%(asctime)s - %(levelname)s: %(message)s')



conn_str  = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=xxxxx;DATABASE=xxxx;UID=xxxx;PWD=xxxxxx"



def get_data_from_db_with_select(start_date, end_date):

    logging.info("Veri çekme işlemi başlatıldı.")

    conn = pyodbc.connect(conn_str)

    engine = create_engine("mssql+pyodbc:///?odbc_connect=" + conn_str)

    query = f"SELECT * FROM dovizkurlari_tcmb WHERE date BETWEEN '{start_date}' AND '{end_date}'"

    df = pd.read_sql(query, engine)

    conn.close()

    logging.info("Veri çekme işlemi tamamlandı.")

    return df





def get_data_from_xml(start_date, end_date):

    logging.info("XML verisi çekme işlemi başlatıldı.")

    current_datee = start_date

    data_list = []

    while current_datee <= end_date:

        if current_datee.weekday() <= 4:

            formatted_current_date = current_datee.strftime("%d%m%Y")

            formatted_current_datee = current_datee.strftime("%Y%m")

            url = f"https://www.tcmb.gov.tr/kurlar/{formatted_current_datee}/{formatted_current_date}.xml"

            data = get_exchange_rates(url)

            if data:

                data_list.extend(data)



        current_datee += timedelta(days=1)

    df = pd.DataFrame(data_list)

    logging.info("XML verisi çekme işlemi tamamlandı.")

    return df





def get_data_for_today():

    logging.info("Bugünkü veri çekme işlemi başlatıldı.")

    url = "https://www.tcmb.gov.tr/kurlar/today.xml"

    data = get_exchange_rates(url)

    df = pd.DataFrame(data)

    logging.info("Bugünkü veri çekme işlemi tamamlandı.")

    return df





def get_exchange_rates(url):

    logging.info(f"{url} adresinden veri çekme işlemi başlatıldı.")

    exchange_rates = []

    response = requests.get(url)

    if response.status_code == 200:

        soup = BeautifulSoup(response.content, "xml")

        currencies = soup.find_all("Currency")

        date_attribute = soup.find("Tarih_Date")["Date"]





        for currency in currencies:

            currencyCode = currency.get("Kod")

            name = currency.find("Isim").text



            forex_buying_rate = currency.find("ForexBuying").text.replace(",", ".")

            forex_selling_rate = currency.find("ForexSelling").text.replace(",", ".")

            banknote_buying_rate = currency.find("BanknoteBuying").text.replace(",", ".")

            banknote_selling_rate = currency.find("BanknoteSelling").text.replace(",", ".")



            if all([forex_selling_rate, forex_buying_rate]):

                forex_buying_rate = float(forex_buying_rate)

                forex_selling_rate = float(forex_selling_rate)



                banknote_buying_rate = str(banknote_buying_rate) if pd.notna(banknote_buying_rate) else None

                banknote_selling_rate = str(banknote_selling_rate) if pd.notna(banknote_selling_rate) else None

                create_update_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                exchange_rate = {

                    "Date": date_attribute,

                    "CurrencyCode": currencyCode,

                    "Name": name,

                    "Alis": forex_buying_rate,

                    "Satis": forex_selling_rate,

                    "EfektifAlis": banknote_buying_rate,

                    "EfektifSatis": banknote_selling_rate,

                    "CreateDate": create_update_date,

                    "UpdateDate": create_update_date,



                }

                exchange_rates.append(exchange_rate)

        logging.info(f"{url} adresinden veri çekme işlemi tamamlandı.")

        return exchange_rates

    else:

        logging.error(f"{url} adresine bağlantı sağlanamadı.")

        return exchange_rates





def delete_data_from_db(start_date, end_date):

    logging.info("Veri silme işlemi başlatıldı.")

    conn = pyodbc.connect(conn_str)

    delete_query = "DELETE FROM dovizkurlari_tcmb WHERE date BETWEEN ? AND ?"

    conn.execute(delete_query, start_date, end_date)

    conn.commit()

    conn.close()

    logging.info("Veri silme işlemi tamamlandı.")





def insert_into_data_to_db(df):

    logging.info("Veri ekleme işlemi başlatıldı.")

    engine = create_engine("mssql+pyodbc:///?odbc_connect=" + conn_str)

    table_name_sql = 'dovizkurlari_tcmb'

    try:

        df.to_sql(name=table_name_sql, con=engine, if_exists='append', index=False)



        logging.info("Veri başarıyla eklendi.")

    except Exception as e:

        logging.error(f"Veri eklenirken bir hata oluştu: {e}")

    finally:

        engine.dispose()

        logging.info("Veri ekleme işlemi tamamlandı.")





def compare_and_update_db(db_df, xml_df, start_date, end_date):

    logging.info("Veri karşılaştırma ve güncelleme işlemi başlatıldı.")

    result_df = pd.merge(xml_df, db_df, on=['Date', 'CurrencyCode', 'Alis', 'Satis'], how='outer', indicator=True)

    count_same_rows = result_df.shape[0]



    logging.info(f"Aynı olan satır sayısı: {count_same_rows}")

    df_grouped = db_df.groupby('Date')['CreateDate'].max().reset_index()



    if db_df.shape[0] != count_same_rows and xml_df.shape[0] <= count_same_rows:

        delete_data_from_db(start_date, end_date)



        merged_df = pd.merge(xml_df, df_grouped[['Date', 'CreateDate']], on='Date', how='left', suffixes=('_df2', '_df1'))

        merged_df.rename(columns={'CreateDate_df1': 'CreateDate'}, inplace=True)

        merged_df.drop(columns=['CreateDate_df2'], inplace=True)



        nat_rows = pd.isna(merged_df['CreateDate'])

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        merged_df.loc[nat_rows, 'CreateDate'] = now



        insert_into_data_to_db(merged_df)

        logging.info("Veri güncelleme işlemi tamamlandı.")

    else:

        logging.info("Aynı satır sayısı nedeniyle veri güncelleme işlemi yapılmadı.")





if __name__ == "__main__":

    end_date_string = datetime.now().strftime("%Y-%m-%d")

    end_date = datetime.strptime(end_date_string, "%Y-%m-%d")



    start_date = datetime.now() - timedelta(days=7)

    start_date_string = start_date.strftime("%Y-%m-%d")



    db_df = get_data_from_db_with_select(start_date, end_date)

    xml_df = get_data_from_xml(start_date, end_date)



    db_df["Date"] = pd.to_datetime(db_df["Date"])

    xml_df["Date"] = pd.to_datetime(xml_df["Date"], format="%m/%d/%Y")



    compare_and_update_db(db_df, xml_df, start_date, end_date)



    today_data = get_data_for_today()

    insert_into_data_to_db(today_data)



