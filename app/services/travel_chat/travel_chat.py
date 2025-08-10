"""
Travel Chat Service - Multilingual Hotel List

Multilingual hotel list service that supports English, French, and Bangla.
"""

import re
import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from .travel_chat_schema import ChatResponse, HotelInfo, DestinationInfo

logger = logging.getLogger(__name__)

class TravelChatService:
    def __init__(self):
        # Import settings based on your project structure
        try:
            from app.core.config import settings
        except ImportError:
            try:
                from core.config import settings
            except ImportError:
                # Fallback - you can set these directly or from environment
                import os
                class Settings:
                    amadeus_api_key = os.getenv("AMADEUS_API_KEY")
                    amadeus_api_secret = os.getenv("AMADEUS_API_SECRET") 
                    amadeus_base_url = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
                    groq_api_key = os.getenv("GROQ_API_KEY")  # AI API key
                settings = Settings()
        
        # Amadeus config
        self.client_id = settings.amadeus_api_key
        self.client_secret = settings.amadeus_api_secret
        self.base_url = settings.amadeus_base_url
        self.token = None
        self.token_expiry = None
        
        # AI config  
        self.groq_api_key = settings.groq_api_key
        self.groq_base_url = "https://api.groq.com/openai/v1"

    async def get_access_token(self) -> str:
        """Get or refresh Amadeus API access token"""
        if self.token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.token

        url = f"{self.base_url}/v1/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data, headers=headers)
            if response.status_code != 200:
                raise ConnectionError(f"Failed to get access token: {response.text}")
            
            token_data = response.json()
            self.token = token_data["access_token"]
            self.token_expiry = datetime.now() + timedelta(seconds=token_data["expires_in"] - 300)
            return self.token

    async def detect_language_and_extract_city(self, message: str) -> Tuple[str, Optional[str]]:
        """Detect language and extract city name from user message"""
        try:
            if not self.groq_api_key:
                return self.fallback_language_detection(message)
                
            prompt = f"""
            Analyze this message and return ONLY a JSON object with language and city:
            
            Message: "{message}"
            
            Extract:
            1. language: "english", "french", or "bangla" 
            2. city: city name in English (or null if no city found)
            
            Examples:
            "I want hotels in Dhaka" → {{"language": "english", "city": "Dhaka"}}
            "Je veux des hôtels à Paris" → {{"language": "french", "city": "Paris"}}
            "আমি ঢাকার হোটেল চাই" → {{"language": "bangla", "city": "Dhaka"}}
            "Je cherche des hôtels à Cox's Bazar" → {{"language": "french", "city": "Cox's Bazar"}}
            "Montrez-moi des hôtels à Tokyo" → {{"language": "french", "city": "Tokyo"}}
            "Hello" → {{"language": "english", "city": null}}
            "Bonjour" → {{"language": "french", "city": null}}
            
            Return only valid JSON.
            """
            
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 100
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.groq_base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(content)
                    return parsed.get("language", "english"), parsed.get("city")
                else:
                    return self.fallback_language_detection(message)
                    
        except Exception as e:
            logger.error(f"AI language detection error: {str(e)}")
            return self.fallback_language_detection(message)

    def fallback_language_detection(self, message: str) -> Tuple[str, Optional[str]]:
        """Fallback language detection using simple patterns"""
        message_lower = message.lower()
        
        # Language detection patterns
        french_indicators = ['je veux', 'des hôtels', 'à', 'montrez-moi', 'je cherche', 'bonjour', 'dans']
        bangla_indicators = ['আমি', 'হোটেল', 'চাই', 'দেখতে', 'খুঁজছি', 'হ্যালো']
        
        detected_language = "english"  # default
        
        # Check for French
        if any(indicator in message_lower for indicator in french_indicators):
            detected_language = "french"
        # Check for Bangla
        elif any(indicator in message for indicator in bangla_indicators):
            detected_language = "bangla"
        
        # Extract city using patterns based on detected language
        city = None
        if detected_language == "french":
            city = self.extract_city_french(message)
        elif detected_language == "bangla":
            city = self.extract_city_bangla(message)
        else:
            city = self.extract_city_english(message)
        
        return detected_language, city

    def extract_city_english(self, message: str) -> Optional[str]:
        """Extract city from English message"""
        patterns = [
            r'hotel(?:s)? in ([^,.\n]+?)(?:\s|$|,|\.)',
            r'hotels? (?:at|from) ([^,.\n]+?)(?:\s|$|,|\.)',
            r'(?:find|search|show|get) hotel(?:s)? in ([^,.\n]+?)(?:\s|$|,|\.)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return match.group(1).strip().title()
        return None

    def extract_city_french(self, message: str) -> Optional[str]:
        """Extract city from French message"""
        patterns = [
            r'hôtels?\s+à\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'des\s+hôtels?\s+à\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'hôtels?\s+dans\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'cherche.*?hôtels?\s+à\s+([^,.\n]+?)(?:\s|$|,|\.)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return match.group(1).strip().title()
        return None

    def extract_city_bangla(self, message: str) -> Optional[str]:
        """Extract city from Bangla message and convert to English"""
        # Bangla to English city mapping
        city_mapping = {
            'ঢাকা': 'Dhaka',
            'চট্টগ্রাম': 'Chittagong',
            'সিলেট': 'Sylhet',
            'খুলনা': 'Khulna',
            'রাজশাহী': 'Rajshahi',
            'বরিশাল': 'Barisal',
            'রংপুর': 'Rangpur',
            'কক্সবাজার': "Cox's Bazar",
            'দিল্লি': 'Delhi',
            'মুম্বাই': 'Mumbai',
            'কলকাতা': 'Kolkata',
            'প্যারিস': 'Paris',
            'লন্ডন': 'London',
            'টোকিও': 'Tokyo'
        }
        
        # Check for direct city mentions
        for bangla_city, english_city in city_mapping.items():
            if bangla_city in message:
                return english_city
        
        return None

    async def get_city_code(self, city_name: str, access_token: str) -> Optional[str]:
        """Get IATA city code for a city name"""
        try:
            url = f"{self.base_url}/v1/reference-data/locations"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {
                "keyword": city_name,
                "subType": "CITY",
                "page[limit]": "1"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    locations = data.get("data", [])
                    if locations:
                        return locations[0].get("iataCode")
                        
        except Exception as e:
            logger.error(f"Error getting city code for {city_name}: {str(e)}")
        
        return None

    async def get_hotels_by_city(self, city_code: str, access_token: str) -> List[str]:
        """Get list of hotel names by city code"""
        try:
            url = f"{self.base_url}/v1/reference-data/locations/hotels/by-city"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"cityCode": city_code}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    hotels = data.get("data", [])
                    
                    # Extract hotel names
                    hotel_names = []
                    for hotel in hotels[:8]:  # Limit to 8 hotels
                        name = hotel.get("name")
                        if name:
                            hotel_names.append(name)
                    
                    return hotel_names
                else:
                    logger.warning(f"Hotel search failed: {response.status_code} - {response.text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting hotels for city {city_code}: {str(e)}")
            return []

    def get_fallback_hotels(self, city_name: str) -> List[str]:
        """Provide fallback hotel list for common cities"""
        fallback_data = {
            "dhaka": [
                "The Westin Dhaka",
                "InterContinental Dhaka",
                "Pan Pacific Sonargaon",
                "Le Meridien Dhaka",
                "Hotel Sarina",
                "The Cox Today",
                "Hotel 71"
            ],
            "cox's bazar": [
                "Hotel Sea Cox",
                "Long Beach Hotel",
                "Ocean Paradise Hotel",
                "Royal Tulip Sea Pearl",
                "Praasad Paradise Hotel"
            ],
            "chittagong": [
                "Hotel Agrabad",
                "Peninsula Chittagong",
                "The Peninsula Hotel",
                "Hotel Golden Inn"
            ],
            "mumbai": [
                "The Taj Mahal Palace",
                "The Oberoi Mumbai", 
                "Grand Hyatt Mumbai",
                "ITC Maratha",
                "Hotel Marine Plaza"
            ],
            "delhi": [
                "The Imperial New Delhi",
                "Taj Palace New Delhi",
                "The Oberoi New Delhi",
                "ITC Maurya",
                "Hotel Shanker"
            ],
            "paris": [
                "Le Ritz Paris",
                "Four Seasons Hotel George V",
                "Le Meurice",
                "Plaza Athénée",
                "InterContinental Paris"
            ],
            "london": [
                "The Savoy",
                "Claridge's",
                "The Langham",
                "The Shard Hotel",
                "Park Lane Hotel"
            ],
            "tokyo": [
                "The Imperial Hotel",
                "Park Hyatt Tokyo",
                "The Ritz-Carlton Tokyo",
                "Conrad Tokyo",
                "Hotel Okura Tokyo"
            ]
        }
        
        return fallback_data.get(city_name.lower(), [])

    async def generate_multilingual_hotel_response(self, language: str, city_name: str, hotels: List[str]) -> str:
        """Generate AI-powered response in the detected language"""
        try:
            if not self.groq_api_key or not hotels:
                return self.generate_fallback_response(language, city_name, hotels)
                
            hotels_text = "\n".join([f"{i+1}. {hotel}" for i, hotel in enumerate(hotels)])
            
            # Language-specific prompts
            if language == "french":
                prompt = f"""
                Créez une réponse amicale en français pour un voyageur cherchant des hôtels à {city_name}.
                
                Hôtels trouvés:
                {hotels_text}
                
                Créez une réponse qui:
                1. Salue chaleureusement en français
                2. Mentionne la ville demandée
                3. Liste les hôtels de manière attrayante
                4. Ajoute des conseils de voyage utiles
                5. Utilise des émojis appropriés
                6. Reste concis et engageant
                
                Répondez uniquement en français.
                """
            elif language == "bangla":
                prompt = f"""
                {city_name} শহরে হোটেল খুঁজছেন এমন একজন ভ্রমণকারীর জন্য বাংলায় একটি বন্ধুত্বপূর্ণ উত্তর তৈরি করুন।
                
                পাওয়া হোটেলগুলো:
                {hotels_text}
                
                এমন একটি উত্তর তৈরি করুন যেটি:
                1. বাংলায় উষ্ণভাবে অভিবাদন জানায়
                2. অনুরোধ করা শহরের উল্লেখ করে
                3. হোটেলগুলো আকর্ষণীয়ভাবে তালিকাভুক্ত করে
                4. সহায়ক ভ্রমণ টিপস যোগ করে
                5. উপযুক্ত ইমোজি ব্যবহার করে
                6. সংক্ষিপ্ত এবং আকর্ষক রাখে
                
                শুধুমাত্র বাংলায় উত্তর দিন।
                """
            else:  # English
                prompt = f"""
                Create a friendly English response for a traveler looking for hotels in {city_name}.
                
                Hotels found:
                {hotels_text}
                
                Create a response that:
                1. Greets them warmly in English
                2. Mentions the requested city
                3. Lists the hotels attractively
                4. Adds helpful travel tips
                5. Uses appropriate emojis
                6. Keeps it concise and engaging
                
                Respond only in English.
                """
            
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 300
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.groq_base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    return self.generate_fallback_response(language, city_name, hotels)
                    
        except Exception as e:
            logger.error(f"AI response generation error: {str(e)}")
            return self.generate_fallback_response(language, city_name, hotels)

    def generate_fallback_response(self, language: str, city_name: str, hotels: List[str]) -> str:
        """Fallback response in the appropriate language"""
        if not hotels:
            if language == "french":
                return f"Désolé, je n'ai pas pu trouver d'hôtels à {city_name}. Veuillez essayer une autre ville. 🏨"
            elif language == "bangla":
                return f"দুঃখিত, আমি {city_name} এ কোনো হোটেল খুঁজে পাইনি। অন্য একটি শহর চেষ্টা করুন। 🏨"
            else:
                return f"Sorry, I couldn't find any hotels in {city_name}. Please try a different city. 🏨"
        
        if language == "french":
            response = f"🏨 Voici d'excellents hôtels à {city_name}:\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel}\n"
            response += f"\nTotal: {len(hotels)} hôtels trouvés! ✨"
        elif language == "bangla":
            response = f"🏨 {city_name} এর দুর্দান্ত হোটেলগুলো:\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel}\n"
            response += f"\nমোট {len(hotels)}টি হোটেল পাওয়া গেছে! ✨"
        else:
            response = f"🏨 Here are great hotels in {city_name}:\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel}\n"
            response += f"\nTotal {len(hotels)} hotels found! ✨"
        
        return response.strip()

    async def generate_conversational_response(self, language: str, message: str) -> str:
        """Generate conversational responses in the appropriate language"""
        try:
            if not self.groq_api_key:
                return self.get_fallback_conversational_response(language, message)
                
            if language == "french":
                prompt = f"""
                Vous êtes un assistant de voyage amical. Répondez à ce message en français de manière utile.
                
                Message de l'utilisateur: "{message}"
                
                Directives:
                - Soyez amical et utile
                - Si c'est une salutation, répondez chaleureusement et expliquez que vous pouvez aider à trouver des hôtels
                - Si ils demandent de l'aide, expliquez que vous pouvez montrer des listes d'hôtels par ville
                - Gardez les réponses courtes (2-3 phrases max)
                - Utilisez des émojis appropriés
                - Encouragez-les toujours à demander des hôtels dans n'importe quelle ville
                
                Répondez uniquement en français.
                """
            elif language == "bangla":
                prompt = f"""
                আপনি একজন বন্ধুত্বপূর্ণ ভ্রমণ সহায়ক। এই বার্তার সহায়ক উত্তর বাংলায় দিন।
                
                ব্যবহারকারীর বার্তা: "{message}"
                
                নির্দেশনা:
                - বন্ধুত্বপূর্ণ এবং সহায়ক হন
                - যদি এটি একটি অভিবাদন হয়, উষ্ণভাবে উত্তর দিন এবং ব্যাখ্যা করুন যে আপনি হোটেল খুঁজতে সাহায্য করতে পারেন
                - যদি তারা সাহায্য চান, ব্যাখ্যা করুন যে আপনি শহর অনুযায়ী হোটেল তালিকা দেখাতে পারেন
                - উত্তর ছোট রাখুন (সর্বোচ্চ ২-৩ বাক্য)
                - উপযুক্ত ইমোজি ব্যবহার করুন
                - তাদের সর্বদা যেকোনো শহরে হোটেল জিজ্ঞাসা করতে উৎসাহিত করুন
                
                শুধুমাত্র বাংলায় উত্তর দিন।
                """
            else:  # English
                prompt = f"""
                You are a friendly travel assistant. Respond to this message in English helpfully.
                
                User message: "{message}"
                
                Guidelines:
                - Be friendly and helpful
                - If it's a greeting, respond warmly and explain you can help find hotels
                - If they ask for help, explain you can show hotel lists by city
                - Keep responses short (2-3 sentences max)
                - Use appropriate emojis
                - Always encourage them to ask about hotels in any city
                
                Respond only in English.
                """
            
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 150
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.groq_base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    return self.get_fallback_conversational_response(language, message)
                    
        except Exception as e:
            logger.error(f"Conversational AI error: {str(e)}")
            return self.get_fallback_conversational_response(language, message)

    def get_fallback_conversational_response(self, language: str, message: str) -> str:
        """Fallback conversational responses in appropriate language"""
        message_lower = message.lower()
        
        # Greeting detection
        greetings = {
            "english": ['hello', 'hi', 'hey'],
            "french": ['bonjour', 'salut', 'bonsoir'],
            "bangla": ['হ্যালো', 'নমস্কার', 'আস্সালামু আলাইকুম']
        }
        
        # Help detection  
        help_words = {
            "english": ['help', 'what can you do'],
            "french": ['aide', 'aidez-moi', 'que pouvez-vous faire'],
            "bangla": ['সাহায্য', 'সাহায্য চাই', 'কী করতে পারেন']
        }
        
        is_greeting = any(word in message_lower for word in greetings.get(language, []))
        is_help = any(word in message_lower for word in help_words.get(language, []))
        
        if language == "french":
            if is_greeting:
                return "Bonjour! 👋 Je peux vous aider à trouver des hôtels dans n'importe quelle ville du monde. Dites-moi simplement où vous voulez séjourner!"
            elif is_help:
                return "Je peux vous montrer des listes d'hôtels par ville! 🏨 Dites simplement 'Je veux des hôtels à [nom de la ville]'. Essayez: 'Montrez-moi des hôtels à Paris'"
            else:
                return "Je peux vous aider à trouver des hôtels! 🏨 Dites-moi dans quelle ville vous êtes intéressé. Exemple: 'Je veux des hôtels à Tokyo'"
        elif language == "bangla":
            if is_greeting:
                return "হ্যালো! 👋 আমি বিশ্বের যেকোনো শহরে হোটেল খুঁজে দিতে পারি। শুধু বলুন কোথায় থাকতে চান!"
            elif is_help:
                return "আমি শহর অনুযায়ী হোটেল তালিকা দেখাতে পারি! 🏨 শুধু বলুন 'আমি [শহরের নাম] এ হোটেল চাই'। চেষ্টা করুন: 'আমি ঢাকার হোটেল চাই'"
            else:
                return "আমি হোটেল খুঁজে দিতে পারি! 🏨 বলুন কোন শহরে আগ্রহী। উদাহরণ: 'আমি দিল্লির হোটেল চাই'"
        else:  # English
            if is_greeting:
                return "Hello! 👋 I can help you find hotels in any city worldwide. Just tell me where you want to stay!"
            elif is_help:
                return "I can show you hotel lists for any city! 🏨 Just say 'I want hotels in [city name]'. Try: 'Show me hotels in Paris'"
            else:
                return "I can help you find hotels! 🏨 Just tell me which city you're interested in. Example: 'Hotels in London please'"

    async def process_message(self, message: str) -> ChatResponse:
        """Process user message and return multilingual response"""
        try:
            # Detect language and extract city
            language, city_name = await self.detect_language_and_extract_city(message)
            
            if city_name:
                # User wants hotel list for a city
                access_token = await self.get_access_token()
                
                # Get city code
                city_code = await self.get_city_code(city_name, access_token)
                
                if city_code:
                    # Get hotels from Amadeus API
                    hotels = await self.get_hotels_by_city(city_code, access_token)
                else:
                    # Fallback to predefined hotel list
                    hotels = self.get_fallback_hotels(city_name)
                
                # If still no hotels, try fallback
                if not hotels:
                    hotels = self.get_fallback_hotels(city_name)
                
                if hotels:
                    # Create hotel info objects for response
                    hotel_info_list = [
                        HotelInfo(
                            name=hotel,
                            price=None,  # No price in simple version
                            rating=None,  # No rating in simple version
                            location=city_name
                        )
                        for hotel in hotels
                    ]
                    
                    # Generate multilingual AI-powered response
                    response_text = await self.generate_multilingual_hotel_response(language, city_name, hotels)
                    
                    return ChatResponse(
                        response=response_text,
                        hotels=hotel_info_list
                    )
                else:
                    no_results_message = self.generate_fallback_response(language, city_name, [])
                    return ChatResponse(response=no_results_message)
            
            else:
                # Handle general conversation in detected language
                response_text = await self.generate_conversational_response(language, message)
                return ChatResponse(response=response_text)
                    
        except ValueError as e:
            raise e
        except ConnectionError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in process_message: {str(e)}")
            raise

    async def health_check(self) -> bool:
        """Check if the service is healthy"""
        try:
            token = await self.get_access_token()
            return bool(token)
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False