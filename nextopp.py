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
import json
from datetime import datetime

def check_ollama_running():
    """Check if Ollama is running and start it if not"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            st.sidebar.success("✅ Ollama is running")
            return True
    except requests.ConnectionError:
        st.sidebar.warning("⚠️ Ollama is not running. Attempting to start it...")
        try:
            if os.name == 'nt':
                subprocess.Popen(['ollama', 'serve'], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            time.sleep(5)
            response = requests.get("http://localhost:11434/api/tags", timeout=10)
            if response.status_code == 200:
                st.sidebar.success("✅ Ollama started successfully")
                return True
            else:
                st.sidebar.error("❌ Failed to start Ollama automatically")
                return False
        except Exception as e:
            st.sidebar.error(f"❌ Error starting Ollama: {e}")
            st.sidebar.info("💡 Please start Ollama manually: `ollama serve`")
            return False

def get_available_models():
    """Get list of available Ollama models"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'] for model in models]
    except:
        return ["llama2", "mistral", "gemma"]

def extract_post_data(driver, post_element):
    """Extract comprehensive data from a single post"""
    try:
        # Get post text
        post_text = ""
        try:
            # Multiple selectors for post text
            text_selectors = [
                "div[data-ad-comet-preview='true']",
                "div[data-testid='post_message']",
                "div.userContent",
                "div._5rgt._5nk5._5msi",
                "div._5rgt._5nk5",
                "div._5rgt"
            ]
            
            for selector in text_selectors:
                text_elements = post_element.find_elements(By.CSS_SELECTOR, selector)
                if text_elements:
                    post_text = text_elements[0].text.strip()
                    break
        except:
            pass

        # Get author name
        author = "Unknown"
        try:
            author_elements = post_element.find_elements(By.CSS_SELECTOR, "a._6qw4")
            if author_elements:
                author = author_elements[0].text.strip()
        except:
            pass

        # Get time posted
        time_posted = "Unknown"
        try:
            time_elements = post_element.find_elements(By.CSS_SELECTOR, "abbr._5ptz")
            if time_elements:
                time_posted = time_elements[0].get_attribute("title") or time_elements[0].text.strip()
        except:
            pass

        # Get reactions count
        reactions = "0"
        try:
            reaction_elements = post_element.find_elements(By.CSS_SELECTOR, "span._81hb")
            if reaction_elements:
                reactions = reaction_elements[0].text.strip()
        except:
            pass

        # Get comments count
        comments_count = "0"
        try:
            comment_elements = post_element.find_elements(By.CSS_SELECTOR, "span._3dlh")
            if comment_elements:
                comments_count = comment_elements[0].text.strip()
        except:
            pass

        # Get shares count
        shares = "0"
        try:
            share_elements = post_element.find_elements(By.CSS_SELECTOR, "span._3dlj")
            if share_elements:
                shares = share_elements[0].text.strip()
        except:
            pass

        # Extract comments
        comments = []
        try:
            # Click to expand comments if needed
            try:
                view_comments_buttons = post_element.find_elements(By.CSS_SELECTOR, "span._4sxc")
                for button in view_comments_buttons:
                    if "comment" in button.text.lower():
                        driver.execute_script("arguments[0].click();", button)
                        time.sleep(1)
            except:
                pass

            # Extract comments
            comment_elements = post_element.find_elements(By.CSS_SELECTOR, "div._3b-9")
            for comment_element in comment_elements:
                try:
                    comment_author = comment_element.find_element(By.CSS_SELECTOR, "a._6qw4").text.strip()
                    comment_text = comment_element.find_element(By.CSS_SELECTOR, "div._2b1X").text.strip()
                    comment_time = ""
                    try:
                        comment_time_elem = comment_element.find_element(By.CSS_SELECTOR, "abbr._5ptz")
                        comment_time = comment_time_elem.get_attribute("title") or comment_time_elem.text.strip()
                    except:
                        pass
                    
                    comments.append({
                        "author": comment_author,
                        "text": comment_text,
                        "time": comment_time
                    })
                except:
                    continue
        except:
            pass

        return {
            "author": author,
            "text": post_text,
            "time": time_posted,
            "reactions": reactions,
            "comments_count": comments_count,
            "shares": shares,
            "comments": comments
        }

    except Exception as e:
        return {"error": str(e)}

def login_and_scrape_group(email, password, group_url, scroll_count=10, max_posts=50):
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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = uc.Chrome(options=chrome_options)
    all_posts_data = []

    try:
        driver.get("https://www.facebook.com/")
        wait = WebDriverWait(driver, 25)

        # Accept cookies if needed
        try:
            cookie_buttons = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@title, 'Allow all cookies') or contains(text(), 'Allow all cookies') or contains(text(), 'Accept all')]")))
            for button in cookie_buttons:
                try:
                    button.click()
                    time.sleep(2)
                    break
                except:
                    continue
        except:
            pass

        # Login
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "pass")))
        
        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)

        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@name, 'login') or @type='submit']")))
        login_button.click()
        time.sleep(10)

        # Check login success
        if "login_attempt" in driver.current_url or "checkpoint" in driver.current_url:
            st.error("Login verification required. Please check your account.")
            driver.quit()
            return ""

        # Go to group
        driver.get(group_url)
        time.sleep(10)

        # Scroll to load more content
        last_height = driver.execute_script("return document.body.scrollHeight")
        posts_collected = 0
        
        for i in range(scroll_count):
            if posts_collected >= max_posts:
                break
                
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            st.info(f"Scroll {i+1}/{scroll_count} - Loading more posts...")
            time.sleep(4)
            
            # Find and process posts
            post_elements = driver.find_elements(By.CSS_SELECTOR, "div[role='article'], div[data-testid*='post'], div._1xnd")
            
            for post_element in post_elements:
                if posts_collected >= max_posts:
                    break
                    
                try:
                    post_data = extract_post_data(driver, post_element)
                    if post_data and "text" in post_data and post_data["text"]:
                        all_posts_data.append(post_data)
                        posts_collected += 1
                        st.info(f"Collected post {posts_collected}: {post_data['text'][:100]}...")
                except:
                    continue

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Save raw HTML for debugging
        with open("facebook_group_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        driver.quit()

        # Format the extracted data
        formatted_text = format_posts_for_analysis(all_posts_data)
        return formatted_text

    except Exception as e:
        st.error(f"Error during scraping: {str(e)}")
        try:
            driver.quit()
        except:
            pass
        return ""

def format_posts_for_analysis(posts_data):
    """Format the extracted posts data for analysis"""
    formatted_text = ""
    
    for i, post in enumerate(posts_data, 1):
        formatted_text += f"=== POST {i} ===\n"
        formatted_text += f"Author: {post.get('author', 'Unknown')}\n"
        formatted_text += f"Time: {post.get('time', 'Unknown')}\n"
        formatted_text += f"Reactions: {post.get('reactions', '0')}\n"
        formatted_text += f"Comments: {post.get('comments_count', '0')}\n"
        formatted_text += f"Shares: {post.get('shares', '0')}\n"
        formatted_text += f"Content:\n{post.get('text', 'No content')}\n\n"
        
        # Add comments
        comments = post.get('comments', [])
        if comments:
            formatted_text += f"Comments ({len(comments)}):\n"
            for j, comment in enumerate(comments, 1):
                formatted_text += f"  {j}. {comment.get('author', 'Unknown')} ({comment.get('time', '')}): {comment.get('text', '')}\n"
            formatted_text += "\n"
        
        formatted_text += "="*50 + "\n\n"
    
    return formatted_text

def get_text_chunks(text):
    if not text.strip():
        return []
    splitter = CharacterTextSplitter(separator="\n", chunk_size=1500, chunk_overlap=300)
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
        llm = Ollama(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.7,
            top_p=0.9,
            num_predict=1000
        )
        
        memory = ConversationBufferMemory(
            memory_key="chat_history", 
            return_messages=True,
            output_key="answer"
        )
        
        chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
            memory=memory,
            return_source_documents=True,
            output_key="answer"
        )
        
        return chain
        
    except Exception as e:
        st.error(f"Error initializing Ollama: {e}")
        return None

def main():
    st.set_page_config(page_title="Facebook Group Analyzer", page_icon="📘", layout="wide")
    st.title("📘 Advanced Facebook Group Analyzer")
    
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
    if "posts_data" not in st.session_state:
        st.session_state.posts_data = []

    with st.sidebar:
        st.header("⚙️ Configuration")
        
        available_models = get_available_models()
        if available_models:
            model_name = st.selectbox("Select Ollama Model", available_models)
        else:
            model_name = st.text_input("Ollama Model Name", "llama2")
        
        with st.form("login_form"):
            email = st.text_input("📧 Facebook Email")
            password = st.text_input("🔑 Facebook Password", type="password")
            group_url = st.text_input("🌐 Facebook Group URL", placeholder="https://www.facebook.com/groups/groupname/")
            scroll_count = st.slider("🔄 Number of scrolls", 5, 20, 12)
            max_posts = st.slider("📊 Max posts to collect", 10, 100, 30)
            submitted = st.form_submit_button("🚀 Process Facebook Group")

    if submitted:
        if not ollama_running:
            st.error("Ollama is not running. Please start it first.")
        elif not email or not password or not group_url:
            st.warning("Please fill in all fields.")
        else:
            with st.spinner("🕵️‍♂️ Logging in and scraping Facebook group... This may take 3-5 minutes."):
                full_text = login_and_scrape_group(email, password, group_url, scroll_count, max_posts)
                
                if not full_text.strip():
                    st.error("❌ Failed to extract posts. Possible reasons:")
                    st.error("- Login verification required")
                    st.error("- Incorrect group URL/permissions")
                    st.error("- Facebook anti-bot detection")
                else:
                    with st.expander("📋 Preview extracted data"):
                        st.text(full_text[:2000] + "..." if len(full_text) > 2000 else full_text)
                    
                    chunks = get_text_chunks(full_text)
                    if chunks:
                        vectorstore = get_vectorstore(chunks)
                        st.session_state.vectorstore = vectorstore
                        st.session_state.conversation = get_conversation_chain(vectorstore, model_name)
                        
                        if st.session_state.conversation:
                            st.session_state.processed = True
                            st.success(f"✅ Success! Processed {len(chunks)} text chunks from multiple posts with comments.")
                        else:
                            st.error("❌ Failed to initialize conversation chain.")
                    else:
                        st.error("❌ No meaningful text extracted.")

    # Chat interface
    st.header("💬 Chat with Group Data")
    
    if st.session_state.processed:
        user_question = st.chat_input("Ask anything about the group content...")
        
        if user_question:
            if not st.session_state.conversation:
                st.warning("Please process a Facebook group first.")
            else:
                with st.spinner("🤔 Thinking..."):
                    try:
                        response = st.session_state.conversation.invoke({"question": user_question})
                        answer = response.get("answer", "No answer found.")
                        st.session_state.chat_history.append({"question": user_question, "answer": answer})
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.session_state.chat_history.append({
                            "question": user_question, 
                            "answer": "Sorry, I encountered an error. Please try again."
                        })

        # Display chat history
        for chat in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(f"**You:** {chat['question']}")
            with st.chat_message("assistant"):
                st.write(f"**Assistant:** {chat['answer']}")
    else:
        st.info("👈 Please configure and process a Facebook group in the sidebar to start chatting.")

    # Statistics and analysis
    if st.session_state.processed and st.session_state.vectorstore:
        with st.expander("📊 Data Statistics"):
            st.info("Data successfully loaded and ready for analysis!")
            # You can add more statistics here based on the extracted data

if __name__ == "__main__":
    main()