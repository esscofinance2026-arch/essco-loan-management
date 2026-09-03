############################################################################################################################################################
#################################################################     Apply      #######################################################################
############################################################################################################################################################
def apply(request):
    # Get product data from URL parameters
    item_name = request.GET.get('item_name', '')
    item_sku = request.GET.get('item_sku', '')
    item_price = request.GET.get('item_price', '')
    item_url = request.GET.get('item_url', '')
    source = request.GET.get('source', '')
    print("The Product SKU is - ",item_sku," The Product name is ",item_name," The Cost is " ,item_price, " This came from ",item_url)

    form = Essco_Forms.ApplicationForm()

    # ✅ CLEAN THE PRICE: Remove $ and commas
    cleaned_price = item_price
    if cleaned_price:
        # Remove $, commas, and any other non-numeric characters except decimal point
        cleaned_price = cleaned_price.replace('$', '').replace(',', '').strip()
        # Try to convert to float to validate
        try:
            cleaned_price = float(cleaned_price)
        except ValueError:
            cleaned_price = 0.00

    # Initialize form with initial values from WordPress
    initial_data = {}

    # Only set initial values if product data exists
    if item_name:
        # Map product data to form fields
        initial_data['Purchase_Value'] = cleaned_price  # Use price as income

    form = Essco_Forms.ApplicationForm(initial=initial_data)

    if request.method == 'POST':
        form = Essco_Forms.ApplicationForm(request.POST, request.FILES, initial=initial_data)

        if form.is_valid():
            # =============================================================
            # STEP 1: Get IP and location (with fallback)
            # =============================================================
            ip = get_client_ip(request)

            # Try to get location, but don't fail if it doesn't work
            location = f"IP: {ip}"
            try:
                geo = get_geo_location(ip)
                if geo.get('city') != 'Unknown' and geo.get('country') != 'Unknown':
                    location = f"{geo['city']}, {geo['country']} (IP: {ip})"
            except Exception as e:
                logger.warning(f"Could not get location for {ip}: {e}")

            # =============================================================
            # STEP 2: Save application
            # =============================================================
            application = form.save(commit=False)

            # ✅ Add the WordPress data directly to the model
            #if item_name:
                #application.item_name = item_name
                #application.item_sku = item_sku

            if request.user.is_authenticated:
                application.created_by = request.user


            # ✅ DEBUG: Check values before save
            print("=" * 50)
            print("DEBUG: Values BEFORE save")
            print(f"application.item_name: {application.item_name}")
            print(f"application.item_sku: {application.item_sku}")
            print(f"application.Purchase_Value: {application.Purchase_Value}")
            print("=" * 50)
            application.save()

            # =============================================================
            # ✅ STORE THE APPLICATION ID IN THE SESSION
            # =============================================================
            request.session['last_application_id'] = application.id

            # =============================================================
            # ✅ LOG: the application Creation Right after save)
            # =============================================================
            log_action(request=request, user=request.user if request.user.is_authenticated else "Anonymous",
                action='CREATE',  # ✅ Use 'CREATE' action (must exist in your ACTIONS choices)
                application=application,
                description=(
                    f"Application created for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) from {location}"
                ),
                ip_address=ip
            )

            # =============================================================
            # STEP 3: Send confirmation email (separate try block)
            # =============================================================
            print("this is the approval status: ",application.Approval_Status)
            email_sent = False
            try:
                # Clean the value first
                status = application.Approval_Status.strip()

                if (status == "Rejected"):
                    Essco_Emails.send_rejection_email(application)
                elif (status == "Approved Pending"):
                    Essco_Emails.send_application_ap_confirmation(application)
                else:
                    Essco_Emails.send_application_confirmation(application)
                email_sent = True

                logger.info(
                    "EMAIL SENT | Application=%s | User=%s",
                    application.id,
                    request.user.username if request.user.is_authenticated else "Anonymous"
                )

                #messages.success(request, f"pplication submitted! A confirmation email has been sent to {application.email}.")

            except Exception as e:
                logger.exception(
                    "EMAIL FAILED | Application=%s | User=%s | Error: %s",
                    application.id,
                    request.user.username if request.user.is_authenticated else "Anonymous",
                    str(e)
                )

                messages.warning(
                    request,
                    "⚠️ Application submitted but we couldn't send a confirmation email. "
                    "Our team will contact you shortly."
                )

            # =============================================================
            # STEP 4: Log the action
            # =============================================================
            log_action(
                request=request,
                user=request.user if request.user.is_authenticated else "Anonymous",
                action='EMAIL_SENT' if email_sent else 'EMAIL_FAILED',
                application=application,
                description=(
                    f"{'Confirmation email sent to' if email_sent else 'Confirmation email FAILED for'} "
                    f"{application.email} for {application.Fname} {application.Lname} "
                    f"(ID: {application.ID_number}) from {location}"
                ),
                ip_address=ip
            )

            logger.info(
                "APPLICATION CREATED | ID=%s | User=%s",
                application.id,
                request.user.username if request.user.is_authenticated else "Anonymous"
            )

            return redirect('Thank_You')

        else:
            logger.warning(
                "APPLICATION INVALID | User=%s | Errors=%s",
                request.user.username if request.user.is_authenticated else "Anonymous",
                form.errors
            )

    context = {
        # Product data from WordPress
        'item_name': item_name,
        'item_sku': item_sku,
        'item_price': item_price,
        'item_url': item_url,
        'source': source,
        'cleaned_price' : cleaned_price,

        'form': form,
        'is_admin': request.user.is_staff if request.user.is_authenticated else False,
        'is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
    }
    return render(request, "loan_application.html", context)

















    class ApplicationForm(ModelForm):
    accept_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "You must accept the terms to continue."}
    )

    class Meta:
        model = Essco_Models.ApplicationModel
        exclude = ('Total_Monthly_living_expenses','Total_Monthly_debt','Monthly_Obligations','Disposable_Income','Debt_To_Income_Ratio','Living_Expense_Ratio',
        'Total_Debt_Service_Ratio','Approval_Status','Total_Credit_Allowed','Deposit','Financed_Amt','Six','Twelve','Eighteen','Twenty_Four','Thirty','Thirty_Six',
        'created_by','updated_by','Disposable_Income_After','RR','PAYE','NIS','Gross_Monthly_Income_AT')
        widgets = {
            'DOB': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        less_than_six = cleaned_data.get("less_than_six")
        len_employ = cleaned_data.get("Len_Employ")

        if less_than_six == "No" and len_employ == "Less than 6 months":
            raise forms.ValidationError("Invalid employment selection")
        return cleaned_data

    def clean_DOB(self):
        dob = self.cleaned_data.get('DOB')

        if not dob:
            raise forms.ValidationError("Date of Birth is required.")

        # If dob is a string, convert it to date
        if isinstance(dob, str):
            try:
                from datetime import datetime  # Keep this import here if needed
                dob = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError:
                raise forms.ValidationError("Invalid date format. Please use YYYY-MM-DD.")

        # ✅ Use date.today() - date is imported at the top
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        if age < 18:
            raise forms.ValidationError("You must be at least 18 years old to apply.")

        if age > 100:
            raise forms.ValidationError("Please check your date of birth.")

        return dob