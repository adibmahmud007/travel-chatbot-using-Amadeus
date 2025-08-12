

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
            1. language: "english", "french", or "malagasy" 
            2. city: city name in English (or null if no city found)
            
            Examples:
            "I want hotels in Dhaka" → {{"language": "english", "city": "Dhaka"}}
            "Je veux des hôtels à Paris" → {{"language": "french", "city": "Paris"}}
            "Tiako hotely any Antananarivo" → {{"language": "malagasy", "city": "Antananarivo"}}
            "Je cherche des hôtels à Cox's Bazar" → {{"language": "french", "city": "Cox's Bazar"}}
            "Montrez-moi des hôtels à Tokyo" → {{"language": "french", "city": "Tokyo"}}
            "Asehoy hotely any Mumbai" → {{"language": "malagasy", "city": "Mumbai"}}
            "Hello" → {{"language": "english", "city": null}}
            "Bonjour" → {{"language": "french", "city": null}}
            "Manao ahoana" → {{"language": "malagasy", "city": null}}
            
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
        malagasy_indicators = ['tiako', 'hotely', 'any', 'asehoy', 'manao ahoana', 'salama', 'toerana']
        
        detected_language = "english"  # default
        
        # Check for French
        if any(indicator in message_lower for indicator in french_indicators):
            detected_language = "french"
        # Check for Malagasy
        elif any(indicator in message_lower for indicator in malagasy_indicators):
            detected_language = "malagasy"
        
        # Extract city using patterns based on detected language
        city = None
        if detected_language == "french":
            city = self.extract_city_french(message)
        elif detected_language == "malagasy":
            city = self.extract_city_malagasy(message)
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

    def extract_city_malagasy(self, message: str) -> Optional[str]:
        """Extract city from Malagasy message and convert to English"""
        # Malagasy to English city mapping
        city_mapping = {
            'antananarivo': 'Antananarivo',
            'toamasina': 'Toamasina',
            'antsirabe': 'Antsirabe',
            'fianarantsoa': 'Fianarantsoa',
            'mahajanga': 'Mahajanga',
            'toliara': 'Toliara',
            'antsiranana': 'Antsiranana',
            'dhaka': 'Dhaka',
            'mumbai': 'Mumbai',
            'delhi': 'Delhi',
            'paris': 'Paris',
            'london': 'London',
            'tokyo': 'Tokyo',
            'new york': 'New York',
            'sydney': 'Sydney'
        }
        
        # Malagasy city extraction patterns
        patterns = [
            r'hotely\s+any\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'tiako\s+hotely\s+any\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'asehoy\s+hotely\s+any\s+([^,.\n]+?)(?:\s|$|,|\.)',
            r'any\s+([^,.\n]+?)(?:\s|$|,|\.)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                city_found = match.group(1).strip()
                # Check if it's in our mapping
                if city_found in city_mapping:
                    return city_mapping[city_found]
                # Otherwise return as title case
                return city_found.title()
        
        # Check for direct city mentions
        for malagasy_city, english_city in city_mapping.items():
            if malagasy_city in message.lower():
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

    async def get_hotels_by_city(self, city_code: str, access_token: str) -> List[Dict]:
        """Get list of hotels with IDs by city code - REAL DATA ONLY"""
        try:
            url = f"{self.base_url}/v1/reference-data/locations/hotels/by-city"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"cityCode": city_code}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    hotels = data.get("data", [])
                    
                    # Extract hotel info including IDs - REAL DATA ONLY
                    hotel_list = []
                    for hotel in hotels[:8]:  # Limit to 8 hotels
                        name = hotel.get("name")
                        hotel_id = hotel.get("hotelId")
                        if name and hotel_id:
                            hotel_list.append({
                                "name": name,
                                "hotel_id": hotel_id,
                                "address": hotel.get("address", {}),
                                "geoCode": hotel.get("geoCode", {})
                            })
                    
                    return hotel_list
                else:
                    logger.warning(f"Hotel search failed: {response.status_code} - {response.text}")
                    return []  # Return empty if API fails
                    
        except Exception as e:
            logger.error(f"Error getting hotels for city {city_code}: {str(e)}")
            return []  # Return empty if error occurs

    async def get_hotel_rating(self, hotel_id: str, access_token: str) -> Optional[str]:
        """Get hotel rating from Hotel Sentiment API"""
        try:
            url = f"{self.base_url}/v2/e-reputation/hotel-sentiments"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"hotelIds": hotel_id}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Debug logging to see actual response
                    logger.info(f"Rating API response for {hotel_id}: {data}")
                    
                    sentiments = data.get("data", [])
                    
                    if sentiments and len(sentiments) > 0:
                        sentiment = sentiments[0]
                        overall_rating = sentiment.get("overallRating")
                        
                        logger.info(f"Overall rating for {hotel_id}: {overall_rating}")
                        
                        if overall_rating:
                            # Convert rating to stars (1-100 scale to 1-5 stars)
                            stars = round(float(overall_rating) / 20)  # Convert 100 scale to 5 star
                            stars = max(1, min(5, stars))  # Ensure between 1-5
                            return "⭐" * stars + f" ({overall_rating}/100)"
                        else:
                            logger.warning(f"No overallRating found for {hotel_id}")
                            return None
                    else:
                        logger.warning(f"No sentiment data found for {hotel_id}")
                        return None
                else:
                    logger.warning(f"Rating API failed for hotel {hotel_id}: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting rating for hotel {hotel_id}: {str(e)}")
            return None

    async def get_hotels_with_ratings(self, hotels_data: List[Dict], access_token: str) -> List[Dict]:
        """Get hotels with ratings from sentiment API"""
        hotels_with_ratings = []
        
        for hotel in hotels_data:
            hotel_name = hotel["name"]
            hotel_id = hotel["hotel_id"]
            
            # Get rating for this hotel
            rating = await self.get_hotel_rating(hotel_id, access_token)
            
            hotels_with_ratings.append({
                "name": hotel_name,
                "rating": rating or "Rating not available",
                "hotel_id": hotel_id,
                "address": hotel.get("address", {}),
                "geoCode": hotel.get("geoCode", {})
            })
        
        return hotels_with_ratings
        """Generate appropriate 'no hotels found' response in the detected language"""
        if language == "french":
            return f"Désolé, je n'ai pas pu trouver d'hôtels disponibles à {city_name}. Cette ville pourrait ne pas être disponible dans notre base de données ou il pourrait y avoir un problème temporaire. Veuillez essayer une autre ville ou réessayer plus tard. 🏨"
        elif language == "malagasy":
            return f"Miala tsiny, tsy nahita hotely misy any {city_name} aho. Mety tsy misy ity tanàna ity ao amin'ny angon-draharaha na misy olana vonjimaika. Andramo tanàna hafa na avereno indray tatỳ aoriana. 🏨"
        else:  # English
            return f"Sorry, I couldn't find any hotels available in {city_name}. This city might not be available in our database or there might be a temporary issue. Please try a different city or try again later. 🏨"

    def generate_no_hotels_response(self, language: str, city_name: str) -> str:
        """Generate appropriate 'no hotels found' response in the detected language"""
        if language == "french":
            return f"Désolé, je n'ai pas pu trouver d'hôtels disponibles à {city_name}. Cette ville pourrait ne pas être disponible dans notre base de données ou il pourrait y avoir un problème temporaire. Veuillez essayer une autre ville ou réessayer plus tard. 🏨"
        elif language == "malagasy":
            return f"Miala tsiny, tsy nahita hotely misy any {city_name} aho. Mety tsy misy ity tanàna ity ao amin'ny angon-draharaha na misy olana vonjimaika. Andramo tanàna hafa na avereno indray tatỳ aoriana. 🏨"
        else:  # English
            return f"Sorry, I couldn't find any hotels available in {city_name}. This city might not be available in our database or there might be a temporary issue. Please try a different city or try again later. 🏨"

    async def generate_multilingual_hotel_response(self, language: str, city_name: str, hotels: List[Dict]) -> str:
        """Generate AI-powered response in the detected language - REAL DATA ONLY"""
        try:
            if not self.groq_api_key:
                return self.generate_simple_hotel_response(language, city_name, hotels)
                
            hotels_text = "\n".join([f"{i+1}. {hotel['name']} - {hotel['rating']}" for i, hotel in enumerate(hotels)])
            
            # Language-specific prompts
            if language == "french":
                prompt = f"""
                Créez une réponse amicale en français pour un voyageur cherchant des hôtels à {city_name}.
                
                Hôtels trouvés avec notes (données réelles d'Amadeus):
                {hotels_text}
                
                Créez une réponse qui:
                1. Salue chaleureusement en français
                2. Mentionne la ville demandée
                3. Liste les hôtels avec leurs notes de manière attrayante
                4. Indique que ce sont des données réelles d'Amadeus
                5. Utilise des émojis appropriés
                6. Reste concis et engageant
                
                Répondez uniquement en français.
                """
            elif language == "malagasy":
                prompt = f"""
                Mamorona valiny sariaka amin'ny teny Malagasy ho an'ny mpandeha mitady hotely any {city_name}.
                
                Hotely hita miaraka amin'ny naoty (angon-drakitra tena avy amin'ny Amadeus):
                {hotels_text}
                
                Mamorona valiny izay:
                1. Manao veloma amin'ny fomba mafana amin'ny teny Malagasy
                2. Milaza ny tanàna nangatahina
                3. Manome lisitry ny hotely miaraka amin'ny naoty amin'ny fomba mahasarika
                4. Milaza fa angon-drakitra marina avy amin'ny Amadeus izany
                5. Mampiasa emoji mety
                6. Mitazona ny fohy sy mahaliana
                
                Valio amin'ny teny Malagasy ihany.
                """
            else:  # English
                prompt = f"""
                Create a friendly English response for a traveler looking for hotels in {city_name}.
                
                Hotels found with ratings (real data from Amadeus):
                {hotels_text}
                
                Create a response that:
                1. Greets them warmly in English
                2. Mentions the requested city
                3. Lists the hotels with ratings attractively
                4. Indicates these are real Amadeus data
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
                    return self.generate_simple_hotel_response(language, city_name, hotels)
                    
        except Exception as e:
            logger.error(f"AI response generation error: {str(e)}")
            return self.generate_simple_hotel_response(language, city_name, hotels)

    def generate_simple_hotel_response(self, language: str, city_name: str, hotels: List[Dict]) -> str:
        """Simple response when AI is not available - REAL DATA ONLY"""
        if language == "french":
            response = f"🏨 Voici les hôtels disponibles à {city_name} (données réelles d'Amadeus):\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel['name']} - {hotel['rating']}\n"
            response += f"\nTotal: {len(hotels)} hôtels trouvés! ✨"
        elif language == "malagasy":
            response = f"🏨 Ireto ny hotely misy any {city_name} (angon-drakitra marina avy amin'ny Amadeus):\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel['name']} - {hotel['rating']}\n"
            response += f"\nTotaliny: hotely {len(hotels)} no hita! ✨"
        else:
            response = f"🏨 Here are available hotels in {city_name} (real data from Amadeus):\n\n"
            for i, hotel in enumerate(hotels, 1):
                response += f"{i}. {hotel['name']} - {hotel['rating']}\n"
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
            elif language == "malagasy":
                prompt = f"""
                Ianao dia mpanampy dia sariaka. Valio ity hafatra ity amin'ny teny Malagasy amin'ny fomba mahasoa.
                
                Hafatry ny mpampiasa: "{message}"
                
                Torolalana:
                - Aoka ho sariaka sy mahasoa
                - Raha fiarahabana izany, manaova veloma mafana ary hazavao fa afaka manampy hitady hotely ianao
                - Raha mitady fanampiana izy ireo, hazavao fa afaka mampiseho lisitry ny hotely isaky ny tanàna ianao
                - Ataovy fohy ny valiny (fehezanteny 2-3 fara fahabetsany)
                - Mampiasà emoji mety
                - Amporisiho hatrany izy ireo hangataka hotely amin'ny tanàna rehetra
                
                Valio amin'ny teny Malagasy ihany.
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
        
    def get_fallback_conversational_response(self, language: str, message: str) -> str:
        """Fallback conversational responses in appropriate language"""
        message_lower = message.lower()
        
        # Greeting detection
        greetings = {
            "english": ['hello', 'hi', 'hey'],
            "french": ['bonjour', 'salut', 'bonsoir'],
            "malagasy": ['manao ahoana', 'salama', 'akory']
        }
        
        # Help detection  
        help_words = {
            "english": ['help', 'what can you do'],
            "french": ['aide', 'aidez-moi', 'que pouvez-vous faire'],
            "malagasy": ['fanampiana', 'ampianao', 'inona no vitanao']
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
        elif language == "malagasy":
            if is_greeting:
                return "Manao ahoana! 👋 Afaka manampy anao hitady hotely any amin'ny tanàna rehetra eran'izao tontolo izao aho. Lazao fotsiny hoe aiza no tianao hivonana!"
            elif is_help:
                return "Afaka mampiseho lisitry ny hotely isaky ny tanàna aho! 🏨 Lazao fotsiny hoe 'Tiako hotely any [anaran'ny tanàna]'. Andramo: 'Asehoy ny hotely any Antananarivo'"
            else:
                return "Afaka manampy anao hitady hotely aho! 🏨 Lazao ahy hoe amin'ny tanàna inona no liana ianao. Ohatra: 'Tiako hotely any Paris'"
        else:  # English
            if is_greeting:
                return "Hello! 👋 I can help you find hotels in any city worldwide. Just tell me where you want to stay!"
            elif is_help:
                return "I can show you hotel lists for any city! 🏨 Just say 'I want hotels in [city name]'. Try: 'Show me hotels in Paris'"
            else:
                return "I can help you find hotels! 🏨 Just tell me which city you're interested in. Example: 'Hotels in London please'"

    async def process_message(self, message: str) -> ChatResponse:
        """Process user message and return multilingual response - REAL DATA ONLY"""
        try:
            # Detect language and extract city
            language, city_name = await self.detect_language_and_extract_city(message)
            
            if city_name:
                # User wants hotel list for a city - REAL DATA ONLY
                access_token = await self.get_access_token()
                
                # Get city code
                city_code = await self.get_city_code(city_name, access_token)
                
                if not city_code:
                    # City not found in Amadeus database
                    no_city_message = self.generate_no_hotels_response(language, city_name)
                    return ChatResponse(response=no_city_message)
                
                # Get hotels from Amadeus API - REAL DATA ONLY
                hotels_data = await self.get_hotels_by_city(city_code, access_token)
                
                if hotels_data:
                    # Get ratings for hotels
                    hotels_with_ratings = await self.get_hotels_with_ratings(hotels_data, access_token)
                    
                    # Create hotel info objects for response - REAL DATA WITH RATINGS
                    hotel_info_list = [
                        HotelInfo(
                            name=hotel["name"],
                            price=None,  # No price in simple version
                            rating=hotel["rating"],  # Real rating from Amadeus
                            location=city_name
                        )
                        for hotel in hotels_with_ratings
                    ]
                    
                    # Generate multilingual AI-powered response with REAL DATA
                    response_text = await self.generate_multilingual_hotel_response(language, city_name, hotels_with_ratings)
                    
                    return ChatResponse(
                        response=response_text,
                        hotels=hotel_info_list
                    )
                else:
                    # No hotels found in Amadeus API - NO FAKE DATA
                    no_results_message = self.generate_no_hotels_response(language, city_name)
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