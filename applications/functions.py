import os
import uuid

def id_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_") #Replace every space (" ") with an underscore ("_").
    first_name = instance.Fname.replace(" ", "_") #for example instance.Last_Name = "Van Buren" becomes Van_Buren
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/ID/"        f"identification_{unique_name}{ext}")

def Payslip_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Payslip/"        f"Payslip_{unique_name}{ext}")

def Job_Letter_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Job_Letter/"        f"Job_Letter_{unique_name}{ext}")

def Statement_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/POA/"        f"Statement_{unique_name}{ext}")

def Utility_Bill_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/POA/"        f"Utility_Bill_{unique_name}{ext}")

def Selfie_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Selfie/"        f"Selfie_{unique_name}{ext}")

def Financial_Statement_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Self-Employed/"        f"Financial_Statement_{unique_name}{ext}")

def Bank_Statement_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Self-Employed/"        f"Bank_Statement_{unique_name}{ext}")

def Business_Registration_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_")
    first_name = instance.Fname.replace(" ", "_")
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex

    return (f"applications/"        f"{last_name}_{first_name}_{id_number}/Self-Employed/"        f"Business_Registration_{unique_name}{ext}")

def POA_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]

    last_name = instance.Lname.replace(" ", "_") #Replace every space (" ") with an underscore ("_").
    first_name = instance.Fname.replace(" ", "_") #for example instance.Last_Name = "Van Buren" becomes Van_Buren
    id_number = instance.ID_number.replace(" ","_")
    unique_name = uuid.uuid4().hex