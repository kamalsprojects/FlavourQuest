import requests
import tkinter as tk
from tkinter import scrolledtext, messagebox
from fpdf import FPDF
import psycopg2
import psycopg2.extensions
import functools
import time
import os
import webbrowser
from abc import ABC, abstractmethod

# Global variable for sorting direction
sort_order = "ASC"  # Initial sort order

# Retry decorator for resilient API requests
def retry(attempts=3, delay=2):
    def wrapper_func(func):
        @functools.wraps(func)
        def retry_logic(*args, **kwargs):
            nonlocal attempts, delay
            last_exception = None
            for _ in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"An error occurred: {e}. Retrying in {delay} seconds.")
                    last_exception = e
                    time.sleep(delay)
            raise last_exception
        return retry_logic
    return wrapper_func

# Define Subject interface
class RecipeSubject(ABC):
    @abstractmethod
    def register_observer(self, observer):
        pass

    @abstractmethod
    def remove_observer(self, observer):
        pass

    @abstractmethod
    def notify_observers(self):
        pass

# Define Observer interface
class RecipeObserver(ABC):
    @abstractmethod
    def update(self):
        pass

# Database Repository
class RecipeRepository(RecipeSubject):
    def __init__(self, db_config):
        self.connection = psycopg2.connect(**db_config)
        self.connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.cursor = self.connection.cursor()
        self.ensure_table_exists()
        self.observers = []

    def ensure_table_exists(self):
        create_table_query = """
        CREATE TABLE IF NOT EXISTS recipes (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            ingredients TEXT NOT NULL,
            instructions TEXT,
            source_url TEXT NOT NULL
        );
        """
        self.cursor.execute(create_table_query)

    def save_recipe(self, recipe):
        ingredients = ', '.join([ingredient['original'] for ingredient in recipe['extendedIngredients']])
        instructions = recipe.get('instructions', 'No instructions provided.')
        sql = """INSERT INTO recipes (title, ingredients, instructions, source_url) VALUES (%s, %s, %s, %s)"""
        self.cursor.execute(sql, (recipe['title'], ingredients, instructions, recipe['sourceUrl']))
        messagebox.showinfo("Save Successful", "The recipe was saved successfully.")
        self.notify_observers()  # Notify observers after saving a recipe

    def get_all_recipes(self):
        sql = """SELECT title, ingredients, instructions, source_url FROM recipes"""
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def delete_recipe(self, recipe):
        sql = """DELETE FROM recipes WHERE title = %s"""
        self.cursor.execute(sql, (recipe[0],))
        messagebox.showinfo("Delete Successful", "The recipe was deleted successfully.")
        self.notify_observers()  # Notify observers after deleting a recipe

    def close(self):
        self.cursor.close()
        self.connection.close()

    def register_observer(self, observer):
        self.observers.append(observer)

    def remove_observer(self, observer):
        self.observers.remove(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer.update()

# Fetch and display recipes with specific tags
@retry(attempts=3, delay=2)
def fetch_and_display_recipes(tags=''):
    global current_recipes
    url = f'https://api.spoonacular.com/recipes/random?number=5&tags={tags}&apiKey=d233f6e9bbb94c2c82b6054f2152d214'
    response = requests.get(url)
    response.raise_for_status()  # Will trigger retry if request fails
    data = response.json()
    current_recipes = data['recipes']  # Save fetched recipes for sorting
    display_recipes()

# Toggle sort order and refresh recipe display
def toggle_sort_order():
    global sort_order
    sort_order = "DESC" if sort_order == "ASC" else "ASC"
    display_recipes()

# GUI for displaying recipes and save option, now with sorting
def display_recipes():
    global current_recipes, sort_order
    output_text.config(state=tk.NORMAL)
    output_text.delete(1.0, tk.END)
    
    # Sort recipes based on global sort_order variable
    sorted_recipes = sorted(current_recipes, key=lambda x: x['title'], reverse=(sort_order == "DESC"))
    
    for i, recipe in enumerate(sorted_recipes, start=1):
        recipe_text = f"Recipe {i}:\nTitle: {recipe['title']}\nIngredients: {', '.join([ingredient['original'] for ingredient in recipe['extendedIngredients']])}\nInstructions: {recipe.get('instructions', 'Instructions not provided.')}\nWebsite: {recipe['sourceUrl']}\n"
        output_text.insert(tk.END, recipe_text)
        
        # Create clickable link for website
        website_link = tk.Label(output_text, text=recipe['sourceUrl'], fg="blue", cursor="hand2")
        website_link.bind("<Button-1>", lambda event, url=recipe['sourceUrl']: open_website(url))
        output_text.window_create(tk.END, window=website_link)
        
        save_button = tk.Button(output_text, text="Save Recipe", command=lambda r=recipe: save_recipe_callback(r))
        save_button_pdf = tk.Button(output_text, text="Download PDF", command=lambda r=recipe: save_recipe_pdf(r))
        
        output_text.window_create(tk.END, window=save_button)
        output_text.window_create(tk.END, window=save_button_pdf)
        output_text.insert(tk.END, "\n\n")
    output_text.config(state=tk.DISABLED)

# Callback to save a selected recipe
def save_recipe_callback(recipe):
    repository.save_recipe(recipe)

# Callback to save a selected recipe as PDF
def save_recipe_pdf(recipe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=recipe['title'], ln=True, align="C")
    pdf.ln(10)
    pdf.multi_cell(0, 10, txt=f"Ingredients: {', '.join([ingredient['original'] for ingredient in recipe['extendedIngredients']])}")
    pdf.multi_cell(0, 10, txt=f"Instructions: {recipe.get('instructions', 'Instructions not provided.')}")
    pdf.multi_cell(0, 10, txt=f"Website: {recipe['sourceUrl']}")
    
    # Get the path to the Downloads directory
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    
    # Construct the path for the PDF file
    pdf_file_path = os.path.join(downloads_dir, f"{recipe['title']}.pdf")
    
    # Save the PDF file
    pdf.output(pdf_file_path)
    
    # Show a message box with the file path
    messagebox.showinfo("Download PDF", f"The recipe PDF has been saved to:\n{pdf_file_path}.")

# Callback to delete a selected recipe
def delete_recipe_callback(recipe):
    if messagebox.askyesno("Delete Recipe", "Are you sure you want to delete this recipe?"):
        repository.delete_recipe(recipe)
        display_all_recipes()  # Refresh the displayed recipes after deletion

# Function to display all recipes from the database
def display_all_recipes():
    output_text.config(state=tk.NORMAL)
    output_text.delete(1.0, tk.END)
    recipes = repository.get_all_recipes()
    for i, recipe in enumerate(recipes, start=1):
        recipe_text = f"Recipe {i}:\nTitle: {recipe[0]}\nIngredients: {recipe[1]}\nInstructions: {recipe[2]}\nWebsite: {recipe[3]}\n"
        output_text.insert(tk.END, recipe_text)
        
        # Create clickable link for website
        website_link = tk.Label(output_text, text=recipe[3], fg="blue", cursor="hand2")
        website_link.bind("<Button-1>", lambda event, url=recipe[3]: open_website(url))
        output_text.window_create(tk.END, window=website_link)
        
        # Add delete button for each recipe
        delete_button = tk.Button(output_text, text="Delete", command=lambda r=recipe: delete_recipe_callback(r))
        output_text.window_create(tk.END, window=delete_button)
        
        output_text.insert(tk.END, "\n\n")
    output_text.config(state=tk.DISABLED)

# Callback to open website link in a browser
def open_website(url):
    webbrowser.open_new(url)

current_recipes = []  # Initialize an empty list to store the current recipes

# GUI setup
root = tk.Tk()
root.title("Flavour Quest")
root.geometry("800x600")

# Main frame
main_frame = tk.Frame(root)
main_frame.pack(expand=True, fill=tk.BOTH)

# Buttons frame
buttons_frame = tk.Frame(main_frame)
buttons_frame.pack(side=tk.TOP, padx=10, pady=10)

# Buttons for fetching and sorting recipes
fetch_button = tk.Button(buttons_frame, text="Fetch Random Recipes", command=lambda: fetch_and_display_recipes())
fetch_button.pack(side=tk.LEFT, padx=5)

sort_button = tk.Button(buttons_frame, text="Toggle Sort Order (A-Z / Z-A)", command=toggle_sort_order)
sort_button.pack(side=tk.LEFT, padx=5)

vegetarian_button = tk.Button(buttons_frame, text="Vegetarian Recipes", command=lambda: fetch_and_display_recipes("vegetarian"))
vegetarian_button.pack(side=tk.LEFT, padx=5)

meat_button = tk.Button(buttons_frame, text="Meat Recipes", command=lambda: fetch_and_display_recipes("meat"))
meat_button.pack(side=tk.LEFT, padx=5)

breakfast_button = tk.Button(buttons_frame, text="Breakfast Recipes", command=lambda: fetch_and_display_recipes("breakfast"))
breakfast_button.pack(side=tk.LEFT, padx=5)

view_all_button = tk.Button(buttons_frame, text="View Saved Recipes", command=display_all_recipes)
view_all_button.pack(side=tk.LEFT, padx=5)

# Output text area
output_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=20)
output_text.pack(expand=True, fill='both', padx=10, pady=10)

# Initialize database connection
db_config = {
    "dbname": "FlavourQuest",
    "user": "postgres",
    "password": "projectM--",
    "host": "localhost"
}

repository = RecipeRepository(db_config)

# Run the GUI event loop
root.mainloop()

# Close the database connection when the application exits
repository.close()
