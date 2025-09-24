import streamlit as st
import time
from bs4 import BeautifulSoup
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import FAISS
from langchain_community.llms.ollama import Ollama
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import Document
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def login_and_scrape_group(email, password, group_url, scroll_count=5):
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Stealth flags to reduce detection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument("--ignore-certificate-errors")

    driver = uc.Chrome(options=chrome_options)

    try:
        driver.get("https://www.facebook.com/")

        wait = WebDriverWait(driver, 20)

        # Wait for email and password fields
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "pass")))

        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)

        # Wait for and click the login button
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@type="submit"]')))
        login_button.click()

        # Wait for login to complete - adjust time or add more checks if needed
        time.sleep(10)

        # Go to the Facebook group page
        driver.get(group_url)
        time.sleep(8)

        # Scroll down multiple times to load more posts
        for _ in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

        # Save page source for debugging
        with open("facebook_group_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Find posts by role=article and extract text paragraphs
        posts = soup.find_all("div", {"role": "article"})
        all_text = ""
        for post in posts:
            paragraphs = post.find_all("p")
            post_text = " ".join(p.get_text(strip=True) for p in paragraphs)
            if post_text:
                all_text += post_text + "\n\n"

        driver.quit()
        return all_text

    except Exception as e:
        driver.quit()
        st.error(f"Error during scraping: {e}")
        return ""


def get_text_chunks(text):
    splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=200)
    return splitter.split_text(text)


def get_vectorstore(text_chunks):
    documents = [Document(page_content=chunk) for chunk in text_chunks]
    vectorstore = FAISS.from_documents(documents, SentenceTransformerEmbeddings(model_name='all-MiniLM-L6-v2'))
    return vectorstore


def get_conversation_chain(vectorstore, model_name="llama2"):
    llm = Ollama(model=model_name)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    chain = ConversationalRetrievalChain.from_llm(llm=llm, retriever=vectorstore.as_retriever(), memory=memory)
    return chain


def main():
    st.title("Facebook Group Info Chatbot")

    if "conversation" not in st.session_state:
        st.session_state.conversation = None
    if "vectorstore" not in st.session_state:
        st.session_state.vectorstore = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.form("login_form"):
        email = st.text_input("Facebook Email")
        password = st.text_input("Facebook Password", type="password")
        group_url = st.text_input("Facebook Group URL (e.g., https://www.facebook.com/groups/yourgroupid/)")
        submitted = st.form_submit_button("Process Facebook Group")

    if submitted:
        if not email or not password or not group_url:
            st.warning("Please fill in all fields.")
        else:
            with st.spinner("Logging in and scraping Facebook group... This may take a while."):
                full_text = login_and_scrape_group(email, password, group_url)
                if not full_text.strip():
                    st.error("Failed to extract posts. Check login or group URL.")
                else:
                    chunks = get_text_chunks(full_text)
                    vectorstore = get_vectorstore(chunks)
                    st.session_state.vectorstore = vectorstore
                    st.session_state.conversation = get_conversation_chain(vectorstore)
                    st.success("Group data processed! You can now ask questions.")

    user_question = st.chat_input("Ask a question about the Facebook group:")

    if user_question:
        if not st.session_state.conversation:
            st.warning("Please process a Facebook group first.")
        else:
            response = st.session_state.conversation.invoke({"question": user_question})
            answer = response.get("answer", "No answer found.")
            st.session_state.chat_history.append({"question": user_question, "answer": answer})

    for chat in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(chat["question"])
        with st.chat_message("assistant"):
            st.write(chat["answer"])


if __name__ == "__main__":
    main()
