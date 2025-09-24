import streamlit as st
import time
from bs4 import BeautifulSoup
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import FAISS
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import Document
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from langchain_community.llms.ollama import Ollama
import re
import requests
import subprocess
import os
from typing import List

def check_ollama_running():
    """Check if Ollama is running and start it if not"""
    try:
        # Try to connect to Ollama
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            st.sidebar.success("✅ Ollama is running")
            return True
    except requests.ConnectionError:
        st.sidebar.warning("⚠️ Ollama is not running. Attempting to start it...")
        try:
            # Start Ollama (Windows)
            if os.name == 'nt':  # Windows
                subprocess.Popen(['ollama', 'serve'], 
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:  # Linux/Mac
                subprocess.Popen(['ollama', 'serve'], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
            
            # Wait for Ollama to start
            time.sleep(5)
            
            # Check again
            response = requests.get("http://localhost:11434/api/tags", timeout=10)
            if response.status_code == 200:
                st.sidebar.success("✅ Ollama started successfully")
                return True
            else:
                st.sidebar.error("❌ Failed to start Ollama automatically")
                return False
                
        except Exception as e:
            st.sidebar.error(f"❌ Error starting Ollama: {e}")
            st.sidebar.info("💡 Please start Ollama manually by running: `ollama serve` in your terminal")
            return False

def get_available_models():
    """Get list of available Ollama models"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'] for model in models]
    except:
        return ["llama2", "mistral", "gemma"]  # Default suggestions

def login_and_scrape_group(email, password, group_url, scroll_count=5):
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = uc.Chrome(options=chrome_options)

    try:
        driver.get("https://www.facebook.com/")
        wait = WebDriverWait(driver, 20)

        # Check if we need to accept cookies first
        try:
            cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@title, 'Allow all cookies') or contains(text(), 'Allow all cookies')]")))
            cookie_button.click()
            time.sleep(2)
        except:
            pass

        # Wait for email and password fields
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "pass")))

        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)

        # Wait for and click the login button
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@name, 'login') or @type='submit']")))
        login_button.click()

        # Wait for login to complete
        time.sleep(8)

        # Check for login issues
        if "login_attempt" in driver.current_url or "checkpoint" in driver.current_url:
            st.error("Facebook is asking for additional verification. Please check your account.")
            driver.quit()
            return ""

        # Go to the Facebook group page
        driver.get(group_url)
        time.sleep(8)

        # Check if we're actually in the group
        if "groups" not in driver.current_url:
            st.error("Could not access the group. Please check the URL and your permissions.")
            driver.quit()
            return ""

        # Scroll down multiple times to load more posts
        for i in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            st.info(f"Scrolling to load more posts... ({i+1}/{scroll_count})")
            time.sleep(4)

        # Save page source for debugging
        with open("facebook_group_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Multiple strategies to find posts
        all_text = ""
        
        # Strategy 1: Look for divs with specific data attributes
        post_divs = soup.find_all("div", {"role": "article"})
        if not post_divs:
            # Strategy 2: Look for divs with common Facebook post classes
            post_divs = soup.find_all("div", class_=re.compile(r"userContent|post|story"))
        
        if not post_divs:
            # Strategy 3: Look for divs with specific data-testid
            post_divs = soup.find_all("div", {"data-testid": re.compile(r"post|story")})
        
        st.info(f"Found {len(post_divs)} potential posts")
        
        for i, post in enumerate(post_divs):
            # Try multiple strategies to extract text from posts
            text_elements = []
            
            # Look for paragraphs
            paragraphs = post.find_all("p")
            text_elements.extend([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            
            # Look for divs with text content
            divs_with_text = post.find_all("div", string=True)
            text_elements.extend([div.get_text(strip=True) for div in divs_with_text if div.get_text(strip=True) and len(div.get_text(strip=True)) > 20])
            
            # Look for spans with text content
            spans_with_text = post.find_all("span", string=True)
            text_elements.extend([span.get_text(strip=True) for span in spans_with_text if span.get_text(strip=True) and len(span.get_text(strip=True)) > 20])
            
            # Remove duplicates and join
            if text_elements:
                post_text = " ".join(list(dict.fromkeys(text_elements)))  # Preserve order while removing duplicates
                all_text += f"POST {i+1}: {post_text}\n\n"

        driver.quit()
        return all_text

    except Exception as e:
        st.error(f"Error during scraping: {str(e)}")
        try:
            driver.quit()
        except:
            pass
        return ""

def get_text_chunks(text):
    if not text.strip():
        return []
    splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=200)
    return splitter.split_text(text)

def get_vectorstore(text_chunks):
    if not text_chunks:
        return None
    documents = [Document(page_content=chunk) for chunk in text_chunks]
    vectorstore = FAISS.from_documents(documents, SentenceTransformerEmbeddings(model_name='all-MiniLM-L6-v2'))
    return vectorstore

def get_conversation_chain(vectorstore, model_name="llama2"):
    if vectorstore is None:
        return None
    
    try:
        # Initialize Ollama with proper configuration
        llm = Ollama(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.7,
            top_p=0.9,
            num_predict=500
        )
        
        memory = ConversationBufferMemory(
            memory_key="chat_history", 
            return_messages=True,
            output_key="answer"
        )
        
        chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            memory=memory,
            return_source_documents=True,
            output_key="answer"
        )
        
        return chain
        
    except Exception as e:
        st.error(f"Error initializing Ollama: {e}")
        st.info("Please make sure Ollama is running: `ollama serve`")
        return None

def main():
    st.set_page_config(page_title="Facebook Group Info Chatbot", page_icon="📘")
    st.title("📘 Facebook Group Info Chatbot with Ollama")
    
    # Check if Ollama is running
    ollama_running = check_ollama_running()
    
    # Initialize session state
    if "conversation" not in st.session_state:
        st.session_state.conversation = None
    if "vectorstore" not in st.session_state:
        st.session_state.vectorstore = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "processed" not in st.session_state:
        st.session_state.processed = False

    with st.sidebar:
        st.header("Configuration")
        
        # Model selection
        available_models = get_available_models()
        if available_models:
            model_name = st.selectbox("Select Ollama Model", available_models)
        else:
            model_name = st.text_input("Ollama Model Name", "llama2")
        
        with st.form("login_form"):
            email = st.text_input("Facebook Email")
            password = st.text_input("Facebook Password", type="password")
            group_url = st.text_input("Facebook Group URL", placeholder="https://www.facebook.com/groups/groupname/")
            scroll_count = st.slider("Number of scrolls to load posts", 3, 10, 5)
            submitted = st.form_submit_button("Process Facebook Group")

    if submitted:
        if not ollama_running:
            st.error("Ollama is not running. Please start it first.")
        elif not email or not password or not group_url:
            st.warning("Please fill in all fields.")
        else:
            with st.spinner("Logging in and scraping Facebook group... This may take 1-2 minutes."):
                full_text = login_and_scrape_group(email, password, group_url, scroll_count)
                
                if not full_text.strip():
                    st.error("Failed to extract posts. This could be due to:")
                    st.error("1. Login verification required")
                    st.error("2. Incorrect group URL")
                    st.error("3. No permission to access the group")
                    st.error("4. Facebook's anti-bot detection")
                else:
                    # Show a preview of the extracted text
                    with st.expander("Preview extracted text"):
                        st.text(full_text[:1000] + "..." if len(full_text) > 1000 else full_text)
                    
                    chunks = get_text_chunks(full_text)
                    if chunks:
                        vectorstore = get_vectorstore(chunks)
                        st.session_state.vectorstore = vectorstore
                        st.session_state.conversation = get_conversation_chain(vectorstore, model_name)
                        
                        if st.session_state.conversation:
                            st.session_state.processed = True
                            st.success(f"Group data processed! Found {len(chunks)} text chunks. You can now ask questions.")
                        else:
                            st.error("Failed to initialize conversation chain. Check Ollama.")
                    else:
                        st.error("No meaningful text could be extracted from the group.")

    # Chat interface
    st.header("Chat with Group Data")
    
    if st.session_state.processed:
        user_question = st.chat_input("Ask a question about the Facebook group:")
        
        if user_question:
            if not st.session_state.conversation:
                st.warning("Please process a Facebook group first.")
            else:
                with st.spinner("Thinking..."):
                    try:
                        response = st.session_state.conversation.invoke({"question": user_question})
                        answer = response.get("answer", "No answer found.")
                        st.session_state.chat_history.append({"question": user_question, "answer": answer})
                    except Exception as e:
                        st.error(f"Error generating response: {e}")
                        st.session_state.chat_history.append({
                            "question": user_question, 
                            "answer": "Sorry, I encountered an error. Please check if Ollama is running properly."
                        })

        # Display chat history
        for chat in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(chat["question"])
            with st.chat_message("assistant"):
                st.write(chat["answer"])
    else:
        st.info("Please configure and process a Facebook group in the sidebar to start chatting.")

    # Add some troubleshooting tips
    with st.expander("Ollama Troubleshooting Tips"):
        st.markdown("""
        ### If Ollama is not working:
        
        1. **Start Ollama manually**:
           ```bash
           ollama serve
           ```
        
        2. **Check available models**:
           ```bash
           ollama list
           ```
        
        3. **Pull a model if needed**:
           ```bash
           ollama pull llama2
           ```
        
        4. **Check if Ollama is running**:
           ```bash
           curl http://localhost:11434/api/tags
           ```
        
        5. **Common models to try**:
           - `llama2` (most common)
           - `mistral`
           - `gemma`
           - `phi`
        """)

if __name__ == "__main__":
    main()