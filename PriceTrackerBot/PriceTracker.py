import sys, os, requests, re, random, datetime, sqlite3, time, telegram, threading
os.chdir(sys.path[0]) 
from bs4 import BeautifulSoup
from AuthInfo import API_TOKEN
from lxml.html import fromstring
from telegram.ext import MessageHandler, InlineQueryHandler, CommandHandler, Updater, ConversationHandler, RegexHandler
import telegram.ext
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')    #Turn on to view telegram bot log in console
from logging.handlers import RotatingFileHandler
logger=logging.getLogger(__name__)
handler=RotatingFileHandler('PriceTracker.log', maxBytes=100000, backupCount=1)
logger.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.info("Program started.")
os.chdir(sys.path[0]) 


class PriceTracker():
    
    def __init__(self, API_TOKEN):
        self.HEADERS={r'User-Agent': r"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36"}

        self.CreateProxyList()
        while not self.ProxyList:
            logger.info("Couldn't create ProxyList, retrying...")
            time.sleep(25)
            self.CreateProxyList()
        print(self.ProxyList)
        logger.info(str(self.ProxyList))
        self.InitializeDatabase()
        self.TelegramBot=telegram.Bot(token=API_TOKEN)
        self.Updater=Updater(token=API_TOKEN)
        self.Dispatcher=self.Updater.dispatcher
        logger.info('Telegram bot connected.')




        

    def Exit(self):
        self.Database.close()





    def GetAmazonProductInfo(self, link, max_tries=5): #Returns a dictionary with Name, Price, Date, Link
        link=self.CorrectLink(link)  #test

        for tries in range(0,max_tries):
            try:
                try:
                    x=random.randint(0, len(self.ProxyList)-1)
                    proxy=self.ProxyList[x]
                    logger.info("Using proxy: " + str(proxy))
                    r=requests.get(link, headers=self.HEADERS, proxies={"http": proxy, "https": proxy}, timeout=15.0)
                    #open('page.html', 'wb').write(r.content) #For debug purposes
                    
                except:

                    logger.error("Error in proxy list, attempting without proxy")
                    r=requests.get(link, headers=self.HEADERS, timeout=5.0)
                
                soup=BeautifulSoup(r.text, 'html5lib')  # USE html5lib only, as r may be a broken html page
                pricetag=soup.find("span", id='priceblock_ourprice')
                if not pricetag:
                    pricetag=soup.find("span", id='priceblock_saleprice')
                if not pricetag:
                    pricetag=soup.find("span", id='priceblock_dealprice')
                nametag=soup.find("span", id="productTitle")
                if not nametag:
                    logger.error("Cant find name tag of product.")
                    raise ValueError("No product name.")
                if not pricetag:
                    logger.error("Can't find pricetag of price.")
                    raise ValueError("No product price")
                logger.info("Name: " + nametag.text.strip())
                logger.info("Price: " + pricetag.text.strip())
                return {'Name': nametag.text.strip(),
                        'Price': float(pricetag.text.strip().replace(',','')),
                        'Date': datetime.datetime.now(),
                        'Link': link}
            except Exception as e:
                logger.warning(e)
                time.sleep(3)
                pass
        if tries==max_tries-1:
            logger.error("Could not get product info for: " + link)
            logger.error("Max tries limit reached.")
        



            

    def CorrectLink(self,link):
        #CorrectedLink=re.search("https:\/\/(www\.)?amazon\.\w+\/[a-zA-Z0-9-]+\/\w+\/\w+", link).group()
        CorrectedLink=re.search("https:\/\/(www\.)?amazon\.\w+\/([a-zA-Z0-9-]+\/)?\w+\/\w+", link).group()
        
        if CorrectedLink.endswith('ref'):
            CorrectedLink=CorrectedLink[:-3]

        if not CorrectedLink.endswith('/'):
            CorrectedLink=CorrectedLink+'/'

        if link.endswith('th=1&psc=1'):
            CorrectedLink=CorrectedLink+'&th=1&psc=1?th=1&psc=1/'



            
        logger.info("Corrected link: " + CorrectedLink)
        return CorrectedLink
        #try:
        #    customization=re.search("https:\/\/(www\.)?amazon\.\w+\/[a-zA-Z0-9-]+\/\w+\/\w+\/(.*?)(th=1&psc=1)", link).group()
        #    CorrectedLink=CorrectedLink+'/&th=1&psc=1?th=1&psc=1'
        #except:
        #    return CorrectedLink







    def InitializeDatabase(self):
        Database=sqlite3.connect('Prices.db')
        Cursor=Database.cursor()
        Cursor.execute("SELECT name FROM sqlite_master where type='table' AND name='products'")     #Check if Database exists
        if not Cursor.fetchall():
            logger.info("Creating table for the first time.")
            Cursor.execute('''
                CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, link TEXT, high TEXT, low TEXT)
                ''')
            
            Cursor.execute("CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, chat_id TEXT, product_id TEXT, alert_price TEXT)")

        Database.close()






    def AddPrice(self, ProductInfo):
        #Takes a dictionary, adds it to the database
        #Product info={'Name':name, 'Link':link, 'Date': date, 'Price':price}
        #
        #Database consists of table products containing name and link.
        #For each product in database, there is a table with the name of the product id with the columns date and price, both as TEXT .
        # A table "subscriptions" is created with chat_id and product id to notify users when price drops
        #
        
        Database=sqlite3.connect('Prices.db')
        Cursor=Database.cursor()

        Cursor.execute("SELECT name,link from products WHERE link=(?)", (ProductInfo['Link'],))         #Check if product exists by link search
        if Cursor.fetchall()==[]:
            logger.info("Adding product to database for the first time.")
            Cursor.execute('''INSERT INTO products(name,link,high,low)
                VALUES (?,?,?,?)''', (ProductInfo['Name'], ProductInfo['Link'],ProductInfo['Price'],ProductInfo['Price'])) #insert into Products table
            Cursor.execute("select id from products where link=(?)", (ProductInfo['Link'],))
            product_id=Cursor.fetchall()[0][0]
            
            Cursor.execute('''
                CREATE TABLE "{}"(id INTEGER PRIMARY KEY, date TEXT, price TEXT)'''.format(str(product_id)))  #Create table with name product id


        Cursor.execute("select id,high,low from products where link=(?)", (ProductInfo['Link'],))
        fetched=Cursor.fetchall()
        product_id=fetched[0][0]
        if float(ProductInfo['Price'])<float(fetched[0][2]):
            Cursor.execute("UPDATE products SET low ={} WHERE ID = {}".format(ProductInfo['price'], product_id))
        if float(ProductInfo['Price'])>float(fetched[0][1]):
            Cursor.execute("UPDATE products SET high ={} WHERE ID = {}".format(ProductInfo['price'], product_id))
            
        
        Cursor.execute('''INSERT INTO "{}"(date, price)                                          
            VALUES('{}','{}')'''.format(str(product_id),ProductInfo['Date'], ProductInfo['Price']))                            #insert values
        #self.Cursor.execute('select * from "{}"'.format(str(product_id)))

        Database.commit()
        Database.close()
        logger.info("Changes committed")





    def AddToDatabase(self,link):    #Combines 2 functions to directly add link to database
        try:
            self.AddPrice(self.GetAmazonProductInfo(link))
        except Exception as e:
            logger.error(e)





    def DatabaseAutoupdater(self, UpdateFrequency=12):  #Run as thread; UpdateFrequency is in hours
        def Updater(UpdateFrequency):
            while True:
                Database=sqlite3.connect("Prices.db")
                Cursor=Database.cursor()
                self.CreateProxyList()
                while not self.ProxyList:
                    logger.info("Couldn't create ProxyList, retrying...")
                    time.sleep(60)
                    self.CreateProxyList()

                logger.info("Database update initiated")
                Cursor.execute('''select link from products''')
                ProductLinkList=Cursor.fetchall()
                        
                for ProductLink in ProductLinkList:
                    try:
                        self.AddToDatabase(ProductLink[0])
                    except Exception as e:
                        logger.error(e)  
                Database.commit()
                logger.info("Database update complete.")
                logger.info("Starting price alerts.")
                Cursor.execute('''select id, name,link, high,low FROM products''')
                ProductIdList=Cursor.fetchall()
           
                for ProductId in ProductIdList:
                    try:    
                        Cursor.execute("SELECT chat_id, product_id, alert_price FROM subscriptions where product_id=(?)", (ProductId[0],))
                        subs=Cursor.fetchall()
                        logger.info("Active subscriptions: ")
                        logger.info(str(subs))
                        Cursor.execute("SELECT id, date, price from '{}'".format(ProductId[0]))
                        
                        PriceDB=Cursor.fetchall()
                        CurrentPrice=PriceDB[len(PriceDB)-1][2]        
                        for sub in subs:
                            try:
                                if float(sub[2])>=float(CurrentPrice):
            
                                    self.TelegramBot.send_message(chat_id=sub[0], text="Price alert! \n\nName:" + ProductId[1] + "\n\nCurrent Price: " + CurrentPrice + "\nHigh: " + ProductId[3]+ "\nLow: " +ProductId[4] + "\nAlert Price: " +sub[2] + "\n\n" +ProductId[2])
                                    self.TelegramBot.send_message(chat_id=sub[0], text="You have been unsubscribed from this products updates.")
                                    Cursor.execute("DELETE FROM subscriptions where chat_id=(?) AND product_id=(?)", (sub[0], sub[1]) )
                                    logger.info("Sent price update and deleted subscription.")
                            except Exception as e:
                                logger.error(e)
                    except Exception as e:
                        logger.error(e)
                logger.info("Price alerts complete.")
                Database.commit()
                Database.close()
                time.sleep(UpdateFrequency*3600)

        ThreadProcess=threading.Thread(target=Updater , args=(UpdateFrequency,) )
        ThreadProcess.daemon=False
        ThreadProcess.start()



        

    def GetProductFromDatabase(self, link):  #returns current price, Low , High
        try:
            link=self.CorrectLink(link)
            
        except Exception as e:
            return 'invalid link'
        Database=sqlite3.connect('Prices.db')
        
        Cursor=Database.cursor()
        

        Cursor.execute("SELECT id,name,link from products WHERE link=(?)", (str(link),))

        
        info=Cursor.fetchall()
        if not info:
            self.AddToDatabase(link) 
            #TODO add something here?
            
        Cursor.execute("SELECT id,name,link,high,low from products WHERE link=(?)", (str(link),))
        info=Cursor.fetchall()
        ProductId=str(info[0][0])
        
        ProductName=str(info[0][1])
        Cursor.execute("SELECT id, date, price from '{}'".format(ProductId))
        PriceDB=Cursor.fetchall()
        
        CurrentPrice=PriceDB[len(PriceDB)-1][2]
        LowestPrice=info[0][4]
        HighestPrice=info[0][3]
        Database.commit()
        Database.close()
        return{'Name': ProductName,
                'Current': CurrentPrice,
                'High': HighestPrice,
                'Low': LowestPrice,
                'Link': link,
                'ProductId': ProductId}



    

    def PrintDatabase(self):
        Database=sqlite3.connect("Prices.db")
        Cursor=Database.cursor()
        Cursor.execute("select * from products")
        print(Cursor.fetchall())

        Cursor.execute("select * from subscriptions")
        print(Cursor.fetchall())




    def CreateProxyList(self):
        url = 'https://free-proxy-list.net/'
        response = requests.get(url)
        parser = fromstring(response.text)
        self.ProxyList =[]
        for i in parser.xpath('//tbody/tr')[:20]:
            if i.xpath('.//td[7][contains(text(),"yes")]'):
                #Grabbing IP and corresponding PORT
                proxy = ":".join([i.xpath('.//td[1]/text()')[0], i.xpath('.//td[2]/text()')[0]])
                self.ProxyList.append(proxy)
        if self.ProxyList:
            logger.info("Proxy list created.")

            

            
    def AddSubscription(self, chat_id, product_id, alert_price): #Returns true if already subscribed
        Database=sqlite3.connect("Prices.db")
        Cursor=Database.cursor()
        
        try:
            Cursor.execute("SELECT chat_id,product_id FROM subscriptions WHERE chat_id=(?) AND product_id=(?)", (str(chat_id), product_id)) #CHECK IF ALREADY EXISTS
            if not Cursor.fetchall():
                Cursor.execute("INSERT INTO subscriptions(chat_id, product_id, alert_price) VALUES (?,?,?)", (str(chat_id), product_id, alert_price))
            else:
                return True
        except Exception as e:
            logger.error(e)
        Database.commit()
        Database.close()



        # ---------------------------------- BOT FUNCTIONS -----------------------------

    def InitiateHandlers(self):
        self.start_handler=CommandHandler('start', self.start)                                 #for /start
        self.Dispatcher.add_handler(self.start_handler)
        self.help_handler=CommandHandler('help', self.help)                                 #for /help
        self.Dispatcher.add_handler(self.help_handler)


        

        self.SUBSCRIBE, self.ALERT_PRICE, self.UNSUBSCRIBE_CONFIRM=range(3)

        
        self.conv_handler = ConversationHandler(
                entry_points=[RegexHandler(".*?https:\/\/(www\.)?amazon\.\w+\/([a-zA-Z0-9-]+\/)?\w+\/\w+.*?", self.conv_Link,  pass_chat_data=True,  pass_user_data=True),
                              CommandHandler('unsubscribe', self.conv_UnsubscribeAsk, pass_chat_data=True, pass_user_data=True),
                              MessageHandler(telegram.ext.Filters.text,
                                             self.conv_Done, pass_user_data=True, pass_chat_data=True)],

                states={
                    self.SUBSCRIBE: [RegexHandler('Subscribe',
                                            self.conv_Subscribe,
                                            pass_user_data=True,  pass_chat_data=True),
                               RegexHandler('^No$',
                                            self.conv_Done,
                                            pass_user_data=True,  pass_chat_data=True)
                               ],

                    self.ALERT_PRICE : [MessageHandler(telegram.ext.Filters.text,
                                                  self.conv_SetAlertPrice,
                                                  pass_user_data=True, pass_chat_data=True)
                                    ],

                    self.UNSUBSCRIBE_CONFIRM : [MessageHandler(telegram.ext.Filters.text,
                                                self.conv_UnsubscribeSure,
                                                pass_user_data=True, pass_chat_data=True),
                                           RegexHandler('^No$',
                                                self.conv_DontSubscribe)
                                            ]


                        },

                fallbacks=[MessageHandler(telegram.ext.Filters.text, self.conv_Done, pass_chat_data=True, pass_user_data=True)]
            )

##
        self.Dispatcher.add_handler(self.conv_handler)
        self.Updater.start_polling()
        logger.info("Polling started")
        self.Updater.idle()


        

    def conv_Link(self, bot, update, user_data, chat_data):
            
        bot.sendChatAction(update.message.chat_id, "typing")
        logger.info("conv_Link invoked")
        info=self.GetProductFromDatabase(update.message.text)

        if info=='invalid link':
            bot.send_message(chat_id=update.message.chat_id, text='Please enter a valid link!')
        else:
            txt="Name: " + info['Name'] + "\n\nCurrent Price: " + info['Current'] + "\nHigh price: " + info['High'] + "\nLow Price: " + info['Low']
            bot.send_message(chat_id=update.message.chat_id, text=txt)
            
        try:
            reply_keyboard = [['Subscribe', 'No']]
            bot.send_message(chat_id=update.message.chat_id, text=('Do you wish to recieve pricing alerts for this product?'),
                                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
            chat_data['info']=info
        except Exception as e:
            logger.error(e)
            


        return self.SUBSCRIBE

    

    def conv_DontSubscribe(self, bot, update, user_data, chat_data):
        bot.send_message(chat_id=update.message.chat_id, text='Thanks for using PriceTrackerBot. Enter a valid link to proceed!')
        

    def conv_Subscribe(self, bot, update, user_data, chat_data):
        logger.info("conv_Subscribe invoked")
        bot.send_message(chat_id=update.message.chat_id, text='Enter the price at which you would like to be notified: ')
        return self.ALERT_PRICE
        
        
    def conv_SetAlertPrice(self, bot, update, user_data, chat_data):
        try:
            AlertPrice=str(float(update.message.text))

        except Exception as e:
            logger.info("Invalid alert price! Looping back")
            bot.send_message(chat_id=update.message.chat_id, text='Enter a valid price without using suffixes like "Rs". Only enter a number!')
            return self.ALERT_PRICE

        if self.AddSubscription(update.message.chat_id, chat_data['info']['ProductId'], AlertPrice):
            bot.send_message(chat_id=update.message.chat_id, text='You are already subscribed to this product! \nUnsubscribe and re-add if you want to change the alert price.')
        else:
            bot.send_message(chat_id=update.message.chat_id, text='You are now subscribed to this product!')
        return ConversationHandler.END
    

    def conv_UnsubscribeAsk(self, bot, update, user_data, chat_data):
        chat_id=str(update.message.chat_id)
        
        Database=sqlite3.connect("Prices.db")
        Cursor=Database.cursor()
        
        try:
            Cursor.execute("SELECT product_id FROM subscriptions WHERE chat_id=(?)", (chat_id,))
            subs=Cursor.fetchall()
            if not subs:
                bot.send_message(chat_id, "You do not have any subscriptions!\nYou can subscribe to a product by sending me a link.")
                return ConversationHandler.END
            namelist={}

            reply_keyboard=[]
            for sub in subs:
                sub=sub[0]
                Cursor.execute("SELECT name FROM products where id=(?)", (sub) )
                name=str(Cursor.fetchall()[0][0])
                namelist[name]=sub
                reply_keyboard.append([name])

            bot.send_message(chat_id, "Which product do you want to unsubscribe from?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
            chat_data['namelist']=namelist
            
        except Exception as e:
            logger.error(e)
        Database.commit()
        Database.close()
        return self.UNSUBSCRIBE_CONFIRM

    def conv_UnsubscribeSure(self, bot, update, user_data, chat_data):
        chat_id=str(update.message.chat_id)      
        Database=sqlite3.connect("Prices.db")
        Cursor=Database.cursor()
        
        try:
            Cursor.execute("DELETE FROM subscriptions where chat_id=(?) AND product_id=(?)", (chat_id, chat_data['namelist'][update.message.text]))
            

            bot.send_message(chat_id=update.message.chat_id, text='You are now unsubscribed from this product!')


        except Exception as e:
            logger.error(e)
            bot.send_message(chat_id=update.message.chat_id, text='Something seems to have gone wrong!')
        Database.commit()
        Database.close()
        return ConversationHandler.END

    
    def conv_Done(self, bot, update, user_data, chat_data):
        bot.send_message(chat_id=update.message.chat_id, text='Thanks for using PriceTrackerBot. Enter a valid link to proceed!')
        return ConversationHandler.END




###----------------------------------



    def start(self, bot, update):
        bot.send_message(chat_id=update.message.chat_id, text='I track prices of online products. Send me an Amazon product link!')
        logger.info("/start command invoked.")

    def help(self, bot, update):
        bot.send_message(chat_id=update.message.chat_id, text='Send me a link to get price information or subscribe to alerts! \nUse the command /unsubscribe to unsubscribe from an alert.')
        logger.info("/help command invoked.")
 
        

t=PriceTracker(API_TOKEN)
t.PrintDatabase()

t.DatabaseAutoupdater()
t.InitiateHandlers()



